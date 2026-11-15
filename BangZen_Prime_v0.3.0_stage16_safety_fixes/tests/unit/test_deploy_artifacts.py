"""Tes artefak deploy (installer VPS, unit systemd, profil Termux dan VPS).

Hanya memakai pustaka standar dan tidak mengimpor modul yang butuh httpx, sehingga
tetap bisa dijalankan saat dependensi jaringan belum terpasang.
Tes ini memeriksa isi berkas dan perilaku jalur gagal. Pemasangan nyata di
perangkat atau VPS TIDAK diuji di sini.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "deploy" / "systemd" / "bangzen-prime-monitor.service"
PROFILES = {name: ROOT / "deploy" / "profiles" / f"{name}.env" for name in ("vps_default", "termux_light")}
INSTALL_VPS = ROOT / "scripts" / "install_vps.sh"
RUN_PROFILE = ROOT / "scripts" / "run_monitor_profile.sh"
TERMUX_DOC = ROOT / "docs" / "TERMUX.md"
LIVE_ON = re.compile(r"^\s*BANGZEN_(LIVE_TRADING|BROADCAST_ENABLED)\s*=\s*\"?(true|1|yes)\"?\s*$", re.I | re.M)


def parse_env(path: Path) -> dict:
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def run_bash(script: Path, args=(), cwd=None, env=None):
    base_env = {"PATH": "/usr/bin:/bin"}
    if env:
        base_env.update(env)
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=cwd or ROOT,
        env=base_env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestSystemdTemplate(unittest.TestCase):
    def setUp(self):
        self.text = SERVICE.read_text(encoding="utf-8")

    def test_runs_monitor_in_paper_mode_only(self):
        exec_line = next(line for line in self.text.splitlines() if line.startswith("ExecStart="))
        self.assertIn(" monitor ", exec_line)
        self.assertNotIn("--live", exec_line)
        self.assertNotIn("broadcast", exec_line.lower())
        self.assertFalse(LIVE_ON.search(self.text))

    def test_no_docker_or_native_build_in_unit(self):
        lowered = self.text.lower()
        for word in ("docker", "cargo", "rustc", "maturin"):
            self.assertNotIn(word, lowered)

    def test_restart_and_hardening_are_present(self):
        for line in (
            "Restart=on-failure",
            "NoNewPrivileges=yes",
            "ProtectSystem=strict",
            "ProtectHome=read-only",
            "PrivateTmp=yes",
            "KillSignal=SIGINT",
        ):
            self.assertIn(line, self.text)

    def test_start_limit_keys_sit_in_unit_section(self):
        # systemd mengabaikan StartLimit* jika ditaruh di [Service]. Tes ini mengunci penempatannya.
        section = None
        placed = {}
        for raw in self.text.splitlines():
            line = raw.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
            elif "=" in line and not line.startswith("#"):
                placed[line.split("=", 1)[0]] = section
        self.assertEqual(placed["StartLimitIntervalSec"], "Unit")
        self.assertEqual(placed["StartLimitBurst"], "Unit")
        self.assertEqual(placed["Restart"], "Service")

    def test_placeholders_are_the_only_unfilled_values(self):
        self.assertEqual(
            sorted(set(re.findall(r"__[A-Z_]+__", self.text))),
            ["__APP_DIR__", "__APP_USER__", "__VENV_DIR__"],
        )

    def test_unit_arguments_match_vps_default_profile(self):
        profile = parse_env(PROFILES["vps_default"])
        exec_line = next(line for line in self.text.splitlines() if line.startswith("ExecStart="))
        self.assertIn(f"--interval-seconds {profile['BZ_INTERVAL_SECONDS']}", exec_line)
        self.assertIn(f"--scans-per-minute {profile['BZ_SCANS_PER_MINUTE']}", exec_line)


DAILY_SERVICE = ROOT / "deploy" / "systemd" / "bangzen-prime-daily-report.service"
DAILY_TIMER = ROOT / "deploy" / "systemd" / "bangzen-prime-daily-report.timer"


class TestDailyReportUnits(unittest.TestCase):
    def test_service_is_oneshot_sending_daily_report_paper_only(self):
        text = DAILY_SERVICE.read_text(encoding="utf-8")
        self.assertIn("Type=oneshot", text)
        exec_line = next(line for line in text.splitlines() if line.startswith("ExecStart="))
        self.assertTrue(exec_line.endswith(" daily-report --send"), exec_line)
        self.assertNotIn("--live", exec_line)
        self.assertFalse(LIVE_ON.search(text))
        # Oneshot tidak boleh punya kebijakan restart, supaya kegagalan tidak memicu pengiriman berulang.
        self.assertNotRegex(text, r"^Restart=", "service oneshot must not auto-restart")

    def test_service_placeholders_are_the_standard_three(self):
        text = DAILY_SERVICE.read_text(encoding="utf-8")
        self.assertEqual(
            sorted(set(re.findall(r"__[A-Z_]+__", text))),
            ["__APP_DIR__", "__APP_USER__", "__VENV_DIR__"],
        )

    def test_timer_runs_at_0010_utc_and_targets_service(self):
        text = DAILY_TIMER.read_text(encoding="utf-8")
        self.assertIn("OnCalendar=*-*-* 00:10:00 UTC", text)
        self.assertIn("Unit=bangzen-prime-daily-report.service", text)
        self.assertIn("Persistent=true", text)
        self.assertIn("WantedBy=timers.target", text)

    def test_installer_renders_all_three_units(self):
        text = INSTALL_VPS.read_text(encoding="utf-8")
        for unit in (
            "bangzen-prime-monitor.service",
            "bangzen-prime-daily-report.service",
            "bangzen-prime-daily-report.timer",
        ):
            self.assertIn(unit, text)


DISCOVER_SERVICE = ROOT / "deploy" / "systemd" / "bangzen-prime-discover.service"
DISCOVER_RUNNER = ROOT / "scripts" / "run_discover_profile.sh"


class TestDiscoverUnit(unittest.TestCase):
    def setUp(self):
        self.text = DISCOVER_SERVICE.read_text(encoding="utf-8")

    def test_runs_continuous_discover_paper_only(self):
        exec_line = next(line for line in self.text.splitlines() if line.startswith("ExecStart="))
        self.assertIn(" discover ", exec_line)
        self.assertNotIn("--once", exec_line)  # harus terus berjalan
        self.assertNotIn("--live", exec_line)
        self.assertFalse(LIVE_ON.search(self.text))

    def test_restarts_on_failure_because_it_is_long_running(self):
        self.assertIn("Restart=on-failure", self.text)
        self.assertIn("Type=simple", self.text)

    def test_placeholders_are_the_standard_three(self):
        self.assertEqual(
            sorted(set(re.findall(r"__[A-Z_]+__", self.text))),
            ["__APP_DIR__", "__APP_USER__", "__VENV_DIR__"],
        )

    def test_unit_arguments_match_vps_default_profile(self):
        profile = parse_env(PROFILES["vps_default"])
        exec_line = next(line for line in self.text.splitlines() if line.startswith("ExecStart="))
        self.assertIn(f"--interval-seconds {profile['BZ_DISCOVER_INTERVAL_SECONDS']}", exec_line)
        self.assertIn(f"--limit {profile['BZ_DISCOVER_LIMIT']}", exec_line)

    def test_discover_profile_values_respect_cli_bounds(self):
        for name, path in PROFILES.items():
            values = parse_env(path)
            with self.subTest(profile=name):
                self.assertGreaterEqual(int(values["BZ_DISCOVER_INTERVAL_SECONDS"]), 15)
                self.assertTrue(1 <= int(values["BZ_DISCOVER_LIMIT"]) <= 100)

    def test_termux_discovery_is_lighter(self):
        termux = parse_env(PROFILES["termux_light"])
        vps = parse_env(PROFILES["vps_default"])
        self.assertGreater(int(termux["BZ_DISCOVER_INTERVAL_SECONDS"]), int(vps["BZ_DISCOVER_INTERVAL_SECONDS"]))
        self.assertLess(int(termux["BZ_DISCOVER_LIMIT"]), int(vps["BZ_DISCOVER_LIMIT"]))

    def test_installer_renders_discover_unit(self):
        self.assertIn("bangzen-prime-discover.service", INSTALL_VPS.read_text(encoding="utf-8"))

    def test_discover_runner_rejects_unknown_profile(self):
        result = run_bash(DISCOVER_RUNNER, args=["bogus"])
        self.assertEqual(result.returncode, 2)

    def test_discover_runner_refuses_without_cli_on_path(self):
        result = run_bash(DISCOVER_RUNNER, args=["termux_light"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("tidak ada di PATH", result.stderr)


class TestProfiles(unittest.TestCase):
    def test_profiles_respect_cli_lower_bounds(self):
        for name, path in PROFILES.items():
            values = parse_env(path)
            with self.subTest(profile=name):
                self.assertGreaterEqual(int(values["BZ_INTERVAL_SECONDS"]), 15)
                self.assertGreaterEqual(int(values["BZ_SCANS_PER_MINUTE"]), 1)
                self.assertGreaterEqual(int(values["BZ_MAX_MINTS"]), 1)

    def test_termux_profile_is_lighter_than_vps(self):
        termux = parse_env(PROFILES["termux_light"])
        vps = parse_env(PROFILES["vps_default"])
        self.assertGreater(int(termux["BZ_INTERVAL_SECONDS"]), int(vps["BZ_INTERVAL_SECONDS"]))
        self.assertLess(int(termux["BZ_SCANS_PER_MINUTE"]), int(vps["BZ_SCANS_PER_MINUTE"]))
        self.assertLess(int(termux["BZ_MAX_MINTS"]), int(vps["BZ_MAX_MINTS"]))

    def test_profiles_never_enable_live_or_broadcast(self):
        for path in PROFILES.values():
            self.assertFalse(LIVE_ON.search(path.read_text(encoding="utf-8")), path.name)


class TestShellScripts(unittest.TestCase):
    def test_scripts_pass_bash_syntax_check(self):
        for script in (INSTALL_VPS, RUN_PROFILE):
            with self.subTest(script=script.name):
                result = subprocess.run(
                    ["bash", "-n", str(script)], capture_output=True, text=True, timeout=30
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_install_vps_executes_no_docker_or_sudo(self):
        # Hanya baris eksekusi yang diperiksa. Komentar dan blok pesan instruksi
        # (heredoc MSG) boleh menyebut sudo atau docker karena hanya dicetak.
        executable = []
        in_message = False
        for raw in INSTALL_VPS.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line == "cat <<MSG":
                in_message = True
                continue
            if in_message:
                if line == "MSG":
                    in_message = False
                continue
            if line and not line.startswith("#"):
                executable.append(line)
        for line in executable:
            self.assertFalse(re.match(r"^(sudo|docker|systemctl)\b", line), line)
            self.assertNotIn("| docker", line)

    def test_install_vps_refuses_outside_project_folder(self):
        # Berjalan sebagai root di sandbox, jadi pemeriksaan root lebih dulu. Keduanya
        # tetap berakhir dengan exit 1 dan tidak memasang apa pun.
        with tempfile.TemporaryDirectory() as tmp:
            result = run_bash(INSTALL_VPS, cwd=tmp, env={"HOME": tmp})
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR", result.stderr)
            self.assertFalse(os.path.exists(os.path.join(tmp, "bz-venv")))

    def test_run_profile_rejects_unknown_profile(self):
        result = run_bash(RUN_PROFILE, args=["bogus"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr)

    def test_run_profile_refuses_without_cli_on_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "watchlist.txt").write_text("# kosong\n", encoding="utf-8")
            result = run_bash(RUN_PROFILE, args=["termux_light"], cwd=tmp)
            self.assertEqual(result.returncode, 1)
            self.assertIn("tidak ada di PATH", result.stderr)

    def test_run_profile_enforces_mint_cap_before_running(self):
        if shutil.which("bangzen-prime", path="/usr/bin:/bin"):
            self.skipTest("bangzen-prime ada di PATH; uji batas mint dilewati")
        with tempfile.TemporaryDirectory() as tmp:
            # Jalur ini diuji dengan PATH palsu yang berisi stub bangzen-prime.
            bindir = Path(tmp, "bin")
            bindir.mkdir()
            stub = bindir / "bangzen-prime"
            stub.write_text("#!/bin/sh\necho STUB_RAN\nexit 0\n", encoding="utf-8")
            stub.chmod(0o755)
            mints = "\n".join(f"Mint{i:03d}" for i in range(26))  # 26 > 25 (termux_light)
            Path(tmp, "watchlist.txt").write_text(mints + "\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", str(RUN_PROFILE), "termux_light"],
                cwd=tmp,
                env={"PATH": f"{bindir}:/usr/bin:/bin"},
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("membatasi 25", result.stderr)
            self.assertNotIn("STUB_RAN", result.stdout)


class TestTermuxDoc(unittest.TestCase):
    def test_watchlist_path_matches_repository(self):
        text = TERMUX_DOC.read_text(encoding="utf-8")
        self.assertNotIn("cp config/watchlist.example.txt", text)
        self.assertIn("cp configs/watchlist.example.txt", text)
        self.assertTrue((ROOT / "configs" / "watchlist.example.txt").is_file())

    def test_light_profile_is_marked_unverified(self):
        text = TERMUX_DOC.read_text(encoding="utf-8")
        self.assertIn("BELUM DIVERIFIKASI", text)


if __name__ == "__main__":
    unittest.main()
