import pytest

from webapp.narration_plan import split_sentences


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "O papel era tão fino que... o dedo... ele... atravessou a fronteira. Sem pedir licença.",
            ["O papel era tão fino que... o dedo... ele... atravessou a fronteira.", "Sem pedir licença."],
        ),
        ("Eu saí de lá... mas uma parte de mim ficou.", ["Eu saí de lá... mas uma parte de mim ficou."]),
        ("Eu saí de lá... Banheiro de estrada.", ["Eu saí de lá...", "Banheiro de estrada."]),
        ("Ok… Fim.", ["Ok…", "Fim."]),
        ("Ok… e depois?", ["Ok… e depois?"]),
        ("Primeira frase. Segunda?  Terceira!", ["Primeira frase.", "Segunda?", "Terceira!"]),
    ],
)
def test_ellipsis_only_ends_a_sentence_before_a_capital_letter(text: str, expected: list[str]) -> None:
    assert split_sentences(text) == expected
