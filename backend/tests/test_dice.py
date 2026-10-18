from collections.abc import Iterator

import pytest

from app.dice import DiceError, engine, is_dice_expression, roll


@pytest.fixture
def rigged(monkeypatch: pytest.MonkeyPatch):
    """Make the RNG return a fixed sequence of faces."""

    def install(*faces: int) -> None:
        seq: Iterator[int] = iter(faces)
        monkeypatch.setattr(engine._rng, "randint", lambda low, high: next(seq))

    return install


@pytest.mark.parametrize(
    "text",
    [
        "d4",
        "D20",
        "5d6",
        "1d20+5",
        "2d20kh1",
        "4d6dl1",
        "1d6 + 1d4 - 2",
        "(2d6+3)*2",
        "d%",
        "4dF",
        "3d6!",
        "5d10>8",
        "2d20kl1+3",
        "1d20ro1",
        "8d6sd",
        "10d6!!",
        "3d6!p",
        "5d10>7f1",
    ],
)
def test_valid_dice_expressions(text: str) -> None:
    assert is_dice_expression(text)


@pytest.mark.parametrize(
    "text",
    [
        "hello",
        "5",
        "2+2",
        "d",
        "dice",
        "I rolled 1d20",
        "",
        "1d20 hello",
        "0d6",
        "1d0",
        "kh1",
        "1d1!",
        "1d6r<6",
        "1d6f1",
    ],
)
def test_not_dice_expressions(text: str) -> None:
    assert not is_dice_expression(text)


def test_basic_sum(rigged) -> None:
    rigged(3, 5)
    result = roll("2d6+1")
    assert result.total == 9
    assert result.breakdown == "(3+5)+1"


def test_bare_d_means_one_die(rigged) -> None:
    rigged(4)
    assert roll("d4").total == 4


def test_percentile(rigged) -> None:
    rigged(73)
    assert roll("d%").total == 73


def test_ranges_are_respected() -> None:
    for _ in range(200):
        assert 5 <= roll("5d6").total <= 30
        assert -4 <= roll("4dF").total <= 4


def test_keep_highest(rigged) -> None:
    rigged(4, 17)
    result = roll("2d20kh1")
    assert result.total == 17
    assert [d.kept for d in result.terms[0].dice] == [False, True]


def test_keep_lowest(rigged) -> None:
    rigged(4, 17)
    assert roll("2d20kl1").total == 4


def test_drop_lowest_default(rigged) -> None:
    rigged(6, 1, 4, 3)
    assert roll("4d6d1").total == 13


def test_drop_highest(rigged) -> None:
    rigged(6, 1, 4, 3)
    assert roll("4d6dh1").total == 8


def test_exploding(rigged) -> None:
    rigged(6, 6, 2, 3)
    result = roll("2d6!")
    assert result.total == 17
    assert [d.value for d in result.terms[0].dice] == [6, 6, 2, 3]


def test_exploding_with_target(rigged) -> None:
    rigged(5, 1)
    assert roll("1d6!>5").total == 6


def test_compounding(rigged) -> None:
    rigged(6, 6, 2)
    result = roll("1d6!!")
    assert result.total == 14
    assert len(result.terms[0].dice) == 1


def test_penetrating(rigged) -> None:
    rigged(6, 6, 3)
    # 6 + (6-1) + (3-1)
    assert roll("1d6!p").total == 13


def test_reroll_ones(rigged) -> None:
    rigged(1, 1, 5)
    result = roll("1d6r")
    assert result.total == 5
    assert [d.rerolled for d in result.terms[0].dice] == [True, True, False]


def test_reroll_once(rigged) -> None:
    rigged(1, 1)
    assert roll("1d6ro").total == 1


def test_reroll_with_compare(rigged) -> None:
    rigged(2, 1, 5)
    assert roll("1d6r<2").total == 5


def test_successes(rigged) -> None:
    rigged(8, 3, 10, 7, 9)
    assert roll("5d10>8").total == 3


def test_successes_and_failures(rigged) -> None:
    rigged(8, 1, 10, 1, 5)
    assert roll("5d10>8f1").total == 0


def test_sort_descending(rigged) -> None:
    rigged(2, 6, 4)
    assert [d.value for d in roll("3d6sd").terms[0].dice] == [6, 4, 2]


def test_arithmetic_precedence(rigged) -> None:
    rigged(4)
    assert roll("2+1d6*3").total == 14


def test_division(rigged) -> None:
    rigged(5)
    assert roll("1d6/2").total == 2.5


def test_division_by_zero() -> None:
    with pytest.raises(DiceError):
        roll("1d6/0")


def test_limits() -> None:
    with pytest.raises(DiceError):
        roll("1001d6")
    with pytest.raises(DiceError):
        roll("1d10001")
    with pytest.raises(DiceError):
        roll("1d6+" * 60 + "1")


def test_explosion_is_capped(rigged) -> None:
    rigged(*([6] * (engine.MAX_EXTRA_ROLLS + 1)))
    assert len(roll("1d6!").terms[0].dice) == engine.MAX_EXTRA_ROLLS + 1
