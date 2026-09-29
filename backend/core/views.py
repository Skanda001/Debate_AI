import json
import time
import queue
import threading
import concurrent.futures

from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from .models import Question, ModelResponse, Judgment
from .serializers import QuestionSerializer, UserSerializer
from .services.providers import build_contestants, ProviderError
from .services.judge import judge_responses


@api_view(["GET"])
def health(request):
    return Response({"status": "healthy"})


@api_view(["GET"])
def api_root(request):
    return Response({
        "name": "DEBATE AI API",
        "status": "running",
        "frontend_ui": "http://localhost:5173",
        "endpoints": {
            "health": "/api/health/",
            "auth_register": "/api/auth/register/",
            "auth_login": "/api/auth/login/",
            "auth_me": "/api/auth/me/",
            "auth_logout": "/api/auth/logout/",
            "history": "/api/history/",
            "ask_stream": "/api/ask/stream/?question=...",
        },
    })


def _get_request_user(request):
    if request.user and request.user.is_authenticated:
        return request.user
    token_key = request.GET.get("token") or (request.data.get("token") if hasattr(request, "data") else None)
    if not token_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Token "):
            token_key = auth_header[6:].strip()
    if token_key:
        try:
            token = Token.objects.select_related("user").get(key=token_key)
            return token.user
        except Token.DoesNotExist:
            return None
    return None


@api_view(["POST"])
def auth_register(request):
    username = (request.data.get("username") or "").strip()
    email = (request.data.get("email") or "").strip()
    password = (request.data.get("password") or "").strip()

    if not username or not password:
        return Response({"error": "Username and password are required."}, status=status.HTTP_400_BAD_REQUEST)
    if len(password) < 6:
        return Response({"error": "Password must be at least 6 characters."}, status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(username__iexact=username).exists():
        return Response({"error": "Username is already taken."}, status=status.HTTP_400_BAD_REQUEST)
    if email and User.objects.filter(email__iexact=email).exists():
        return Response({"error": "Email is already registered."}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.create_user(username=username, email=email, password=password)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({
        "token": token.key,
        "user": UserSerializer(user).data,
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def auth_login(request):
    username = (request.data.get("username") or "").strip()
    password = (request.data.get("password") or "").strip()

    if not username or not password:
        return Response({"error": "Username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    if "@" in username:
        user_by_email = User.objects.filter(email__iexact=username).first()
        if user_by_email:
            username = user_by_email.username

    user = authenticate(username=username, password=password)
    if not user:
        return Response({"error": "Invalid username or password."}, status=status.HTTP_400_BAD_REQUEST)

    token, _ = Token.objects.get_or_create(user=user)
    return Response({
        "token": token.key,
        "user": UserSerializer(user).data,
    })


@api_view(["GET"])
def auth_me(request):
    user = _get_request_user(request)
    if not user:
        return Response({"error": "Not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)
    return Response({"user": UserSerializer(user).data})


@api_view(["POST"])
def auth_logout(request):
    user = _get_request_user(request)
    if user:
        Token.objects.filter(user=user).delete()
    return Response({"message": "Logged out successfully"})





def _run_one(provider, prompt):
    start = time.time()
    try:
        text = provider.generate(prompt)
        return {
            "model_id": provider.id,
            "display_name": provider.display_name,
            "response": text,
            "error": None,
            "retry_after": None,
            "latency_ms": int((time.time() - start) * 1000),
        }
    except ProviderError as e:
        return {
            "model_id": provider.id,
            "display_name": provider.display_name,
            "response": "",
            "error": str(e),
            "retry_after": getattr(e, "retry_after", None),
            "latency_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        return {
            "model_id": provider.id,
            "display_name": provider.display_name,
            "response": "",
            "error": str(e),
            "retry_after": None,
            "latency_ms": int((time.time() - start) * 1000),
        }


def _save_judgment(question, results, verdict):
    Judgment.objects.create(
        question=question,
        winner_model_id=verdict.get("winner"),
        reason=verdict.get("reason", ""),
        consensus=verdict.get("consensus", ""),
    )
    scores = {e.get("model"): e for e in verdict.get("evaluations", [])}
    for mr in question.responses.all():
        ev = scores.get(mr.model_id)
        if ev:
            mr.score = ev.get("score")
            mr.verdict = ev.get("verdict", "")
        mr.is_winner = mr.model_id == verdict.get("winner")
        mr.save()


def build_prompt_with_history(current_text, parent_id, user=None, max_turns=3):
    """
    Traverse up the question chain (up to max_turns) and prepend previous questions
    and winning model responses to give multi-turn context.
    Returns: (augmented_prompt, parent_question_or_None)
    """
    if not parent_id:
        return current_text, None

    try:
        parent_id = int(parent_id)
    except (ValueError, TypeError):
        return current_text, None

    turns = []
    curr_id = parent_id
    parent_obj = None
    count = 0

    while curr_id and count < max_turns:
        try:
            q = Question.objects.prefetch_related("responses", "judgment").get(id=curr_id)
            if parent_obj is None:
                parent_obj = q

            # Verify ownership if user is authenticated
            if user and q.user_id and q.user_id != user.id:
                break

            # Find the winning response, or highest scored, or first non-empty response
            winner = None
            if hasattr(q, "judgment") and q.judgment and q.judgment.winner_model_id:
                winner = q.responses.filter(model_id=q.judgment.winner_model_id).first()
            if not winner:
                winner = q.responses.filter(is_winner=True).first()
            if not winner:
                winner = q.responses.filter(response__gt="").first()

            assistant_text = winner.response if winner else ""
            if len(assistant_text) > 800:
                assistant_text = assistant_text[:800] + "… [truncated]"

            turns.append({
                "question": q.text,
                "winner_model": winner.display_name if winner else None,
                "answer": assistant_text,
            })
            curr_id = q.parent_id
            count += 1
        except Question.DoesNotExist:
            break

    if not turns:
        return current_text, parent_obj

    # Reverse turns so they are chronological (oldest to newest)
    turns.reverse()

    history_str = "=== Conversation History ===\n"
    for idx, t in enumerate(turns, 1):
        history_str += f"Turn {idx} User: {t['question']}\n"
        if t['answer']:
            model_info = f" (Winning answer by {t['winner_model']})" if t['winner_model'] else ""
            history_str += f"Turn {idx} Assistant{model_info}: {t['answer']}\n\n"
        else:
            history_str += "\n"

    history_str += f"=== Current Question ===\nUser: {current_text}\n\nPlease answer the current question directly while taking into account the conversation history above."
    return history_str, parent_obj


@api_view(["POST"])
def ask(request):
    prompt = (request.data.get("question") or "").strip()
    if not prompt:
        return Response({"error": "question is required"}, status=status.HTTP_400_BAD_REQUEST)

    contestants = build_contestants()
    if not contestants:
        return Response(
            {"error": "No LLM providers are configured. Check backend/.env (CONTESTANTS)."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    user = _get_request_user(request)
    parent_id = request.data.get("parent_id")
    full_prompt, parent_obj = build_prompt_with_history(prompt, parent_id, user=user)

    question = Question.objects.create(user=user, text=prompt, parent=parent_obj)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(contestants)) as pool:
        results = list(pool.map(lambda p: _run_one(p, full_prompt), contestants))

    for r in results:
        ModelResponse.objects.create(
            question=question,
            model_id=r["model_id"],
            display_name=r["display_name"],
            response=r["response"],
            error=r["error"],
            latency_ms=r["latency_ms"],
        )

    verdict = judge_responses(full_prompt, results)
    _save_judgment(question, results, verdict)

    return Response(QuestionSerializer(question).data, status=status.HTTP_201_CREATED)


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def ask_stream(request):
    prompt = (request.GET.get("question") or "").strip()
    user = _get_request_user(request)
    parent_id = request.GET.get("parent_id")

    if not prompt:
        resp = StreamingHttpResponse(
            iter([_sse("error", {"message": "question is required"})]),
            content_type="text/event-stream",
        )
        resp["Cache-Control"] = "no-cache"
        resp["X-Accel-Buffering"] = "no"
        return resp

    contestants = build_contestants()
    if not contestants:
        resp = StreamingHttpResponse(
            iter([_sse("error", {"message": "No LLM providers are configured. Check backend/.env (CONTESTANTS)."})]),
            content_type="text/event-stream",
        )
        resp["Cache-Control"] = "no-cache"
        resp["X-Accel-Buffering"] = "no"
        return resp

    full_prompt, parent_obj = build_prompt_with_history(prompt, parent_id, user=user)

    def gen():
        question = Question.objects.create(user=user, text=prompt, parent=parent_obj)
        yield _sse("start", {
            "question_id": question.id,
            "parent_id": parent_obj.id if parent_obj else None,
            "question": prompt,
            "models": [{"model_id": c.id, "display_name": c.display_name} for c in contestants],
        })

        q = queue.Queue()
        results_lock = threading.Lock()
        results_by_id = {}

        def run_provider(provider):
            q.put(("model_started", {
                "model_id": provider.id,
                "display_name": provider.display_name,
            }))
            full_text = ""
            error = None
            retry_after = None
            start = time.time()
            try:
                for chunk in provider.stream(full_prompt):
                    full_text += chunk
                    q.put(("model_chunk", {"model_id": provider.id, "chunk": chunk}))
            except ProviderError as e:
                error = str(e)
                retry_after = getattr(e, "retry_after", None)
            except Exception as e:
                error = str(e)

            latency_ms = int((time.time() - start) * 1000)
            with results_lock:
                results_by_id[provider.id] = {
                    "model_id": provider.id,
                    "display_name": provider.display_name,
                    "response": full_text,
                    "error": error,
                    "retry_after": retry_after,
                    "latency_ms": latency_ms,
                }
            q.put(("__done__", provider.id))

        threads = [
            threading.Thread(target=run_provider, args=(c,), daemon=True)
            for c in contestants
        ]
        for t in threads:
            t.start()

        finished = 0
        total = len(contestants)

        while finished < total:
            try:
                event, payload = q.get(timeout=300)
            except queue.Empty:
                break

            if event == "__done__":
                finished += 1
                r = results_by_id.get(payload)
                if r:
                    mr = ModelResponse.objects.create(
                        question=question,
                        model_id=r["model_id"],
                        display_name=r["display_name"],
                        response=r["response"],
                        error=r["error"],
                        latency_ms=r["latency_ms"],
                    )
                    yield _sse("model_finished", {
                        "id": mr.id,
                        "model_id": r["model_id"],
                        "response": r["response"],
                        "error": r["error"],
                        "retry_after": r.get("retry_after"),
                        "latency_ms": r["latency_ms"],
                    })
            else:
                yield _sse(event, payload)

        yield _sse("judge_started", {})

        results = list(results_by_id.values())
        try:
            verdict = judge_responses(full_prompt, results)
        except Exception as e:
            verdict = {
                "evaluations": [],
                "winner": None,
                "reason": f"Judge failed: {e}",
                "consensus": "",
            }

        _save_judgment(question, results, verdict)

        question.refresh_from_db()
        yield _sse("complete", {"result": QuestionSerializer(question).data})

    resp = StreamingHttpResponse(gen(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp


@api_view(["GET"])
def history(request):
    user = _get_request_user(request)
    if user:
        qs = Question.objects.filter(user=user).order_by("-is_pinned", "-created_at")
    else:
        qs = Question.objects.filter(user__isnull=True).order_by("-is_pinned", "-created_at")
    return Response(QuestionSerializer(qs, many=True).data)


@api_view(["GET"])
def detail(request, pk):
    user = _get_request_user(request)
    try:
        if user:
            q = Question.objects.get(pk=pk, user=user)
        else:
            q = Question.objects.get(pk=pk, user__isnull=True)
    except Question.DoesNotExist:
        return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(QuestionSerializer(q).data)


@api_view(["DELETE"])
def delete_question(request, pk):
    user = _get_request_user(request)
    if user:
        Question.objects.filter(pk=pk, user=user).delete()
    else:
        Question.objects.filter(pk=pk, user__isnull=True).delete()
    return Response({"message": "deleted"})


@api_view(["DELETE"])
def clear_history(request):
    user = _get_request_user(request)
    if user:
        Question.objects.filter(user=user).delete()
    else:
        Question.objects.filter(user__isnull=True).delete()
    return Response({"message": "cleared"})


@api_view(["PATCH"])
def toggle_pin(request, pk):
    user = _get_request_user(request)
    try:
        if user:
            q = Question.objects.get(pk=pk, user=user)
        else:
            q = Question.objects.get(pk=pk, user__isnull=True)
    except Question.DoesNotExist:
        return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)
    q.is_pinned = not q.is_pinned
    q.save()
    return Response(QuestionSerializer(q).data)