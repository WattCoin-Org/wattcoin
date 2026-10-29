"""Offline tests for format_watt_amount and watt_balance wallet errors."""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import wattcoin  # noqa: E402


@pytest.fixture
def no_wallet(monkeypatch, tmp_path):
    """No env key, no config file, empty wallet cache, stubbed solana imports."""
    monkeypatch.delenv("WATT_WALLET_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(wattcoin, "_wallet_cache", None)
    # _get_wallet looks for "config" next to the module file
    monkeypatch.setattr(wattcoin, "__file__", str(tmp_path / "wattcoin.py"))

    def stub(name, **attrs):
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, mod)

    stub("solana")
    stub("solana.rpc")
    stub("solana.rpc.api", Client=object)
    stub("solders")
    stub("solders.pubkey", Pubkey=object)
    stub("spl")
    stub("spl.token")
    stub("spl.token.instructions", get_associated_token_address=lambda *a, **k: None)
    stub("spl.token.constants", TOKEN_2022_PROGRAM_ID=None)


@pytest.mark.parametrize("amount, expected", [
    (0, "0 WATT"),
    (1000, "1,000 WATT"),
    (1000.0, "1,000 WATT"),
    (1234.5, "1,234.5 WATT"),
    (1234567.5, "1,234,567.5 WATT"),
])
def test_format_watt_amount(amount, expected):
    assert wattcoin.format_watt_amount(amount) == expected


def test_format_watt_amount_negative():
    with pytest.raises(ValueError):
        wattcoin.format_watt_amount(-1)


def test_watt_balance_raises_wallet_error_without_wallet(no_wallet):
    with pytest.raises(wattcoin.WalletError):
        wattcoin.watt_balance(raise_on_error=True)


def test_watt_balance_returns_zero_without_wallet(no_wallet):
    assert wattcoin.watt_balance(raise_on_error=False) == 0
