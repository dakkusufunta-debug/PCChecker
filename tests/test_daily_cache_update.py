"""価格キャッシュ更新ラッパーの終了コードと認証補完を検証する。"""

import os
import subprocess
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "scripts" / "daily_cache_update.ps1"


def _run_with_fake_commands(tmp_path: Path, deploy_exit: int) -> subprocess.CompletedProcess:
    """外部APIを呼ばず、生成成功後の配信終了コードを再現する。"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python.cmd").write_text(
        "@echo {\"generated_at\":\"test\"} > %2\r\n@exit /b 0\r\n",
        encoding="utf-8",
    )
    (bin_dir / "npx.cmd").write_text(
        f"@exit /b {deploy_exit}\r\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["CLOUDFLARE_API_TOKEN"] = "test-token"
    env["CLOUDFLARE_ACCOUNT_ID"] = "test-account"

    return subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-OutDir",
            str(tmp_path / "out"),
            "-ProjectName",
            "test-project",
        ],
        # タスクスケジューラ同様、リポジトリ外から起動しても動くことを確認する。
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_deploy_failure_is_returned(tmp_path):
    """生成成功後に配信が失敗した場合、その終了コードを返す。"""
    result = _run_with_fake_commands(tmp_path, deploy_exit=17)
    assert result.returncode == 17


def test_deploy_success_returns_zero(tmp_path):
    """生成と配信が両方成功した場合は0を返す。"""
    result = _run_with_fake_commands(tmp_path, deploy_exit=0)
    assert result.returncode == 0


def test_cloudflare_values_are_loaded_from_user_environment():
    """タスク実行時にユーザー環境変数を補完する実装を維持する。"""
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'Import-UserEnvironmentVariable "CLOUDFLARE_API_TOKEN"' in source
    assert 'Import-UserEnvironmentVariable "CLOUDFLARE_ACCOUNT_ID"' in source
    assert '[Environment]::GetEnvironmentVariable($Name, "User")' in source


def test_wrangler_runs_non_interactively():
    """スケジューラー実行でWranglerが対話待ちにならない設定を維持する。"""
    source = SCRIPT.read_text(encoding="utf-8")
    assert '$env:CI = "1"' in source
