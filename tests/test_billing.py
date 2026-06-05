"""Tests for the top-up pack catalogue + subscription plan catalogue."""

import pytest

from dating.bl.billing import HINT_PACKS, PACKS_BY_ID, get_pack_or_error
from dating.bl.plans import PLANS_BY_ID, get_plan_or_error
from dating.utils.error_handler import BadRequestException


def test_topup_packs_match_pricing_page() -> None:
    by_id = {p.id: p for p in HINT_PACKS}
    assert by_id["topup_10"].hints == 10
    assert by_id["topup_10"].price_usd == 6.99
    assert by_id["topup_30"].hints == 30
    assert by_id["topup_100"].hints == 100
    assert by_id["topup_100"].price_usd == 49.99


def test_amount_cents_is_integer() -> None:
    assert PACKS_BY_ID["topup_10"].amount_cents == 699
    assert PACKS_BY_ID["topup_100"].amount_cents == 4999


def test_get_pack_or_error_rejects_unknown() -> None:
    assert get_pack_or_error("topup_10").id == "topup_10"
    with pytest.raises(BadRequestException):
        get_pack_or_error("does_not_exist")


def test_plan_catalogue_has_eight_plans() -> None:
    # 4 tiers × {month, year}.
    assert len(PLANS_BY_ID) == 8
    plus_month = get_plan_or_error("plus_month")
    assert plus_month.tier == "plus"
    assert plus_month.hints_per_cycle == 25
    assert plus_month.price_usd == 9.99
    assert plus_month.is_unlimited is False


def test_ultimate_is_unlimited_with_no_hints() -> None:
    ult = get_plan_or_error("ultimate_year")
    assert ult.is_unlimited is True
    assert ult.hints_per_cycle == 0
    assert ult.price_usd == 499.0


def test_get_plan_or_error_rejects_unknown() -> None:
    with pytest.raises(BadRequestException):
        get_plan_or_error("nope_month")
