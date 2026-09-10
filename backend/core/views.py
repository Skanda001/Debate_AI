import json
import time
import concurrent.futures

from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import Question, ModelResponse, Judgment
from .serializers import QuestionSerializer
from .services.providers import build_contestants
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
            "latency_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        return {
            "model_id": provider.id,
            "display_name": provider.display_name,
            "response": "",
            "error": str(e),
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

    def error_stream(message):
        yield _sse("error", {"message": message})

    if not prompt:
        return StreamingHttpResponse(error_stream("question is required"), content_type="text/event-stream")

    contestants = build_contestants()
    if not contestants:
        return StreamingHttpResponse(
            error_stream("No LLM providers are configured. Check backend/.env (CONTESTANTS)."),
            content_type="text/event-stream",
        )

    def gen():
        question = Question.objects.create(text=prompt)
        yield _sse("start", {
            "question_id": question.id,
            "question": prompt,
            "models": [{"model_id": c.id, "display_name": c.display_name} for c in contestants],
        })

        results = []
        for provider in contestants:
            yield _sse("model_started", {"model_id": provider.id, "display_name": provider.display_name})
            full_text = ""
            error = None
            start = time.time()
            try:
                for chunk in provider.stream(prompt):
                    full_text += chunk
                    yield _sse("model_chunk", {"model_id": provider.id, "chunk": chunk})
            except Exception as e:
                error = str(e)

            latency_ms = int((time.time() - start) * 1000)
            mr = ModelResponse.objects.create(
                question=question,
                model_id=provider.id,
                display_name=provider.display_name,
                response=full_text,
                error=error,
                latency_ms=latency_ms,
            )
            results.append({
                "model_id": provider.id,
                "display_name": provider.display_name,
                "response": full_text,
                "error": error,
            })
            yield _sse("model_finished", {
                "id": mr.id,
                "model_id": provider.id,
                "response": full_text,
                "error": error,
                "latency_ms": latency_ms,
            })

        yield _sse("judge_started", {})
        verdict = judge_responses(prompt, results)
        _save_judgment(question, results, verdict)

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
