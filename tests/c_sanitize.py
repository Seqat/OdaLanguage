import os
import subprocess


TEST_CFLAGS = os.environ.get("ODA_TEST_CFLAGS", "").split()


def _uses_asan() -> bool:
    return any(flag.startswith("-fsanitize=address") for flag in TEST_CFLAGS)


def _merge_sanitizer_options(existing: str | None, *options: str) -> str:
    existing_parts = [part for part in (existing or "").split(":") if part]
    new_keys = {option.split("=", 1)[0] for option in options}
    kept = [
        part for part in existing_parts
        if part.split("=", 1)[0] not in new_keys
    ]
    return ":".join(kept + list(options))


def _run_env(*, disable_leaks: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    if _uses_asan():
        options = ["halt_on_error=1"]
        if disable_leaks:
            options.append("detect_leaks=0")
        env["ASAN_OPTIONS"] = _merge_sanitizer_options(
            env.get("ASAN_OPTIONS"),
            *options,
        )
    return env


def _lsan_ptrace_unavailable(stderr: str | bytes | None) -> bool:
    if isinstance(stderr, bytes):
        stderr = stderr.decode(errors="replace")
    return (
        isinstance(stderr, str)
        and "LeakSanitizer has encountered a fatal error" in stderr
        and "LeakSanitizer does not work under ptrace" in stderr
    )


def run_generated_binary(args, **kwargs):
    try:
        return subprocess.run(args, check=True, env=_run_env(), **kwargs)
    except subprocess.CalledProcessError as exc:
        if _uses_asan() and _lsan_ptrace_unavailable(exc.stderr):
            return subprocess.run(
                args,
                check=True,
                env=_run_env(disable_leaks=True),
                **kwargs,
            )
        raise
