"""Valida a classificacao estruturada de erros de integracao."""

import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import APIConnectionError

from scripts.integration_errors import IntegrationFailure, classify_higgsfield_exception
from scripts.openai_utils import classify_openai_exception, create_text_response


class FakeResponses:
    def __init__(self, response):
        self._response = response

    def create(self, **kwargs):
        return self._response


class FakeClient:
    def __init__(self, response):
        self.responses = FakeResponses(response)


def main():
    print("=" * 50)
    print("TESTE: Integration Errors")
    print("=" * 50)

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    openai_failure = classify_openai_exception(
        APIConnectionError(message="Connection error.", request=request)
    )
    if openai_failure.service != "openai" or openai_failure.code != "connection_error":
        print(f"  x OpenAI connection error nao foi classificado corretamente: {openai_failure}")
        return 1
    if openai_failure.stage != "planning":
        print(f"  x OpenAI stage incorreto: {openai_failure.stage}")
        return 1

    try:
        create_text_response(
            client=FakeClient(
                type(
                    "Response",
                    (),
                    {
                        "status": "incomplete",
                        "incomplete_details": {"reason": "max_output_tokens"},
                        "output_text": "",
                        "output": [],
                    },
                )()
            ),
            model="gpt-5.4-pro",
            instructions="Teste",
            user_input="Teste",
            max_output_tokens=50,
        )
    except IntegrationFailure as failure:
        if failure.code != "empty_or_incomplete_response":
            print(f"  x OpenAI incomplete response nao foi classificada corretamente: {failure}")
            return 1
    else:
        print("  x Resposta incompleta da OpenAI deveria ter gerado IntegrationFailure")
        return 1

    model_failure = classify_higgsfield_exception(RuntimeError("Model not found"))
    if model_failure.code != "model_not_found":
        print(f"  x Model not found nao foi classificado corretamente: {model_failure}")
        return 1

    credits_failure = classify_higgsfield_exception(RuntimeError("Insufficient credits"))
    if credits_failure.code != "insufficient_credits":
        print(f"  x Insufficient credits nao foi classificado corretamente: {credits_failure}")
        return 1
    if credits_failure.auth_confirmed is not True or credits_failure.render_confirmed is not False:
        print(f"  x Flags de credito Higgsfield incorretas: {credits_failure}")
        return 1

    print("  + OpenAI e Higgsfield classificam erros de forma estruturada")
    print("-" * 50)
    print("  + TESTE INTEGRATION ERRORS: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
