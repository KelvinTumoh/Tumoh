"""Production-readiness checks for safe deployment."""

from __future__ import annotations

from ide_core.config.settings import IDESettings


class ProductionReadiness:
    """Inspect settings and report deployment-level warnings."""

    WEAK_SECRET_PATTERNS = (
        "change-me",
        "dev-secret",
        "password",
        "123456",
        "default",
        "placeholder",
    )

    def __init__(self, settings: IDESettings | None = None) -> None:
        self._settings = settings or IDESettings()

    def check(self) -> list[str]:
        """Return a list of warnings; an empty list means no obvious issues."""
        warnings: list[str] = []

        secret = self._settings.jwt_secret
        if len(secret.encode("utf-8")) < 32:
            warnings.append(
                "JWT_SECRET is shorter than 32 bytes; "
                "HMAC-SHA256 recommends at least 32 bytes."
            )

        if any(pattern in secret.lower() for pattern in self.WEAK_SECRET_PATTERNS):
            warnings.append(
                "JWT_SECRET appears to be a placeholder; replace it in production."
            )

        if self._settings.jwt_algorithm.lower() == "none":
            warnings.append("JWT_ALGORITHM 'none' is insecure and must not be used.")

        if not self._settings.enable_security_manager:
            warnings.append(
                "Security manager is disabled; command execution is ungated."
            )

        if self._settings.ide_host == "0.0.0.0" and not self._settings.enable_multi_tenant:
            warnings.append(
                "Server is bound to 0.0.0.0 without multi-tenancy; "
                "ensure a reverse proxy or firewall is in place."
            )

        if not self._settings.log_path:
            warnings.append("LOG_PATH is empty; audit logging is disabled.")

        return warnings
