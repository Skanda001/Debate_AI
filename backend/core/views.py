import json
import time
import queue
import threading
import concurrent.futures

from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import Question, ModelResponse, Judgment
from .serializers import QuestionSerializer
from .services.providers import build_contestants, ProviderError
from .services.judge import judge_responses


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

    question = Question.objects.create(text=prompt)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(contestants)) as pool:
        results = list(pool.map(lambda p: _run_one(p, prompt), contestants))

    for r in results:
        ModelResponse.objects.create(
            question=question,
            model_id=r["model_id"],
            display_name=r["display_name"],
            response=r["response"],
            error=r["error"],
            latency_ms=r["latency_ms"],
        )

    verdict = judge_responses(prompt, results)
    _save_judgment(question, results, verdict)

    return Response(QuestionSerializer(question).data, status=status.HTTP_201_CREATED)


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def ask_stream(request):
    prompt = (request.GET.get("question") or "").strip()

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

    def gen():
        question = Question.objects.create(text=prompt)
        yield _sse("start", {
            "question_id": question.id,
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
                for chunk in provider.stream(prompt):
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
            verdict = judge_responses(prompt, results)
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
    qs = Question.objects.all().order_by("-is_pinned", "-created_at")
    return Response(QuestionSerializer(qs, many=True).data)


@api_view(["GET"])
def detail(request, pk):
    try:
        q = Question.objects.get(pk=pk)
    except Question.DoesNotExist:
        return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(QuestionSerializer(q).data)


@api_view(["DELETE"])
def delete_question(request, pk):
    Question.objects.filter(pk=pk).delete()
    return Response({"message": "deleted"})


@api_view(["DELETE"])
def clear_history(request):
    Question.objects.all().delete()
    return Response({"message": "cleared"})


@api_view(["PATCH"])
def toggle_pin(request, pk):
    try:
        q = Question.objects.get(pk=pk)
    except Question.DoesNotExist:
        return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)
    q.is_pinned = not q.is_pinned
    q.save()
    return Response(QuestionSerializer(q).data)