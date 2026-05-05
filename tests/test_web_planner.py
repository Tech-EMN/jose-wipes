"""Valida o planner OpenAI do web studio com cliente mockado."""

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.config import OPENAI_PLANNER_MODEL
from scripts.integration_errors import IntegrationFailure
from webapp.model_registry import get_model_config
from webapp.planner import plan_web_video
from webapp.schemas import CreateJobRequest


class FakeCompletions:
    def __init__(self, payload, capture):
        self.payload = payload
        self.capture = capture

    def create(self, **kwargs):
        self.capture["kwargs"] = kwargs
        return type(
            "Response",
            (),
            {"output_text": json.dumps(self.payload, ensure_ascii=False)},
        )()


class FakeResponses:
    def __init__(self, payload, capture):
        self.create = FakeCompletions(payload, capture).create


class FakeClient:
    def __init__(self, payload, capture, **_kwargs):
        self.responses = FakeResponses(payload, capture)


def _base_payload():
    return {
        "title": "Aeroporto Sem Drama",
        "enhanced_brief_pt": "Versao melhorada do briefing original.",
        "global_style": "Comercial premium, divertido e masculino.",
        "final_cta_pt": "Jose Wipes. Pronto para qualquer banheiro.",
        "notes": "Plano enxuto para reels.",
        "shots": [
            {
                "shot_number": idx,
                "visual_prompt_en": f"Shot {idx} in a modern airport bathroom with confident male lead and premium ad lighting.",
                "duration_seconds": 5,
                "narration_text_pt": f"Narracao {idx}",
                "voice_persona": "narrador",
                "overlay_text": None,
                "product_overlay": {
                    "ativo": False,
                    "posicao": "centro_inferior",
                    "tamanho_pct": 35,
                    "inicio_seg": 1,
                },
                "notes": "ok",
            }
            for idx in range(1, 7)
        ],
    }


def main():
    print("=" * 50)
    print("TESTE: Web Planner")
    print("=" * 50)

    request = CreateJobRequest(
        resolution="1080p",
        orientation="vertical",
        duration_seconds=30,
        prompt="Quero um anuncio divertido sobre banheiro de aeroporto e use a embalagem do lenco umedecido no final.",
        video_model="kling_3_0",
    )
    model_config = get_model_config("kling_3_0")
    temp_dir = Path(__file__).parent.parent / "output" / "test_web_planner"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        sanitizing_payload = _base_payload()
        sanitizing_payload["shots"][0]["product_overlay"] = {
            "ativo": "sim",
            "posicao": "fora_de_quadro",
            "tamanho_pct": 0,
            "inicio_seg": -2,
        }
        sanitizing_payload["shots"][1]["product_overlay"] = {
            "ativo": True,
            "posicao": "direita",
            "tamanho_pct": 100,
            "inicio_seg": 1,
        }

        capture = {}
        with patch("webapp.planner.OPENAI_API_KEY", "test-key"), patch(
            "webapp.planner.OpenAI",
            side_effect=lambda **kwargs: FakeClient(sanitizing_payload, capture, **kwargs),
        ):
            plan = plan_web_video(
                request,
                "Roteiro em PDF de exemplo",
                model_config,
                artifacts_dir=temp_dir,
            )

        if capture["kwargs"]["model"] != OPENAI_PLANNER_MODEL:
            print(
                f"  x O planner deveria usar {OPENAI_PLANNER_MODEL}, mas usou {capture['kwargs']['model']}"
            )
            return 1

        if len(plan.shots) != 6:
            print(f"  x Quantidade de shots incorreta: {len(plan.shots)}")
            return 1

        system_message = capture["kwargs"]["instructions"].lower()
        if "cineasta" not in system_message or "prendem atencao" not in system_message:
            print("  x O system prompt nao foi atualizado para a persona de cineasta short-form")
            return 1
        if "tamanho_pct" not in system_message or "15 e 75" not in system_message:
            print("  x O system prompt nao reforcou o range valido do overlay")
            return 1

        user_message = capture["kwargs"]["input"]
        if "Roteiro em PDF de exemplo" not in user_message:
            print("  x O contexto do PDF nao foi enviado ao planner")
            return 1
        if '"product_reference_required": true' not in user_message.lower():
            print("  x O planner nao recebeu a flag de referencia do produto")
            return 1

        if plan.shots[0].product_overlay.tamanho_pct != 15:
            print(f"  x tamanho_pct deveria ter sido clampado para 15: {plan.shots[0].product_overlay}")
            return 1
        if plan.shots[0].product_overlay.posicao != "centro_inferior":
            print(f"  x posicao invalida deveria virar centro_inferior: {plan.shots[0].product_overlay}")
            return 1
        if plan.shots[0].product_overlay.inicio_seg != 0:
            print(f"  x inicio_seg negativo deveria virar 0: {plan.shots[0].product_overlay}")
            return 1
        if plan.shots[1].product_overlay.tamanho_pct != 75:
            print(f"  x tamanho_pct deveria ter sido clampado para 75: {plan.shots[1].product_overlay}")
            return 1
        if not plan.shots[-1].product_overlay.ativo:
            print("  x O planner deveria forcar product_overlay no ultimo shot")
            return 1
        if plan.shots[-1].overlay_text != plan.final_cta_pt:
            print("  x CTA final nao foi propagado para o ultimo shot")
            return 1

        raw_artifact = temp_dir / "plano_web_raw.json"
        normalized_artifact = temp_dir / "plano_web_normalizado.json"
        if not raw_artifact.exists() or not normalized_artifact.exists():
            print("  x O planner nao salvou os artefatos raw/normalizado")
            return 1

        normalized_payload = json.loads(normalized_artifact.read_text(encoding="utf-8"))
        first_overlay = normalized_payload["shots"][0]["product_overlay"]
        second_overlay = normalized_payload["shots"][1]["product_overlay"]
        if first_overlay["tamanho_pct"] != 15 or first_overlay["inicio_seg"] != 0:
            print(f"  x Artefato normalizado incorreto no shot 1: {first_overlay}")
            return 1
        if second_overlay["tamanho_pct"] != 75:
            print(f"  x Artefato normalizado incorreto no shot 2: {second_overlay}")
            return 1

        invalid_payload = _base_payload()
        invalid_payload["title"] = ""
        invalid_capture = {}
        with patch("webapp.planner.OPENAI_API_KEY", "test-key"), patch(
            "webapp.planner.OpenAI",
            side_effect=lambda **kwargs: FakeClient(invalid_payload, invalid_capture, **kwargs),
        ):
            try:
                plan_web_video(
                    request,
                    "Roteiro em PDF de exemplo",
                    model_config,
                    artifacts_dir=temp_dir / "invalid_case",
                )
            except IntegrationFailure as failure:
                if failure.service != "openai":
                    print(f"  x Service incorreto para payload invalido: {failure}")
                    return 1
                if failure.stage != "planning":
                    print(f"  x Stage incorreto para payload invalido: {failure}")
                    return 1
                if failure.code != "invalid_planner_payload":
                    print(f"  x Codigo incorreto para payload invalido: {failure}")
                    return 1
            else:
                print("  x Payload invalido deveria gerar IntegrationFailure estruturada")
                return 1

        print("  + Planner usa o melhor modelo, inclui o PDF e corrige payloads invalidos da OpenAI")
        print("  + Artefatos raw/normalizado sao salvos para debug")
        print("-" * 50)
        print("  + TESTE WEB PLANNER: PASSOU")
        return 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
