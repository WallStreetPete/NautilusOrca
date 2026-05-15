"""Decorator-based strategy registry.

Usage::

    from blackorca.strategies.registry import register_strategy
    from blackorca.strategies.base import BlackOrcaStrategy

    @register_strategy("sma_cross")
    class SmaCross(BlackOrcaStrategy):
        ...

Looked up by name in CLI / config / the agent layer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar, TypeVar

from blackorca.strategies.base import BlackOrcaStrategy

S = TypeVar("S", bound=BlackOrcaStrategy)


class StrategyRegistry:
    _registry: ClassVar[dict[str, type[BlackOrcaStrategy]]] = {}

    @classmethod
    def register(cls, name: str, strategy_cls: type[BlackOrcaStrategy]) -> None:
        if name in cls._registry and cls._registry[name] is not strategy_cls:
            raise ValueError(f"strategy name collision: {name!r}")
        cls._registry[name] = strategy_cls

    @classmethod
    def get(cls, name: str) -> type[BlackOrcaStrategy]:
        if name not in cls._registry:
            cls._auto_import()
        if name not in cls._registry:
            raise KeyError(f"unknown strategy: {name!r} (known: {sorted(cls._registry)})")
        return cls._registry[name]

    @classmethod
    def list_strategies(cls) -> list[str]:
        cls._auto_import()
        return sorted(cls._registry)

    @staticmethod
    def _auto_import() -> None:
        """Import all examples so their @register_strategy decorators fire."""
        import importlib
        import pkgutil

        from blackorca.strategies import examples

        for mod_info in pkgutil.iter_modules(examples.__path__):
            importlib.import_module(f"blackorca.strategies.examples.{mod_info.name}")


def register_strategy(name: str) -> Callable[[type[S]], type[S]]:
    def deco(cls: type[S]) -> type[S]:
        StrategyRegistry.register(name, cls)
        return cls

    return deco


__all__ = ["StrategyRegistry", "register_strategy"]
