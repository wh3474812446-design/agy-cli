"""Observable wrapper behavior against a local agy stub; no live model calls."""
import json
import os
from pathlib import Path
import pty
import signal
import socket
import subprocess
import sys
import tempfile
import unittest


WRAPPER = Path(__file__).resolve().parents[1] / "scripts" / "agy-run.sh"
SUCCESS = {
    "conversation_id": "test-conversation",
    "status": "SUCCESS",
    "response": "PONG\n",
    "duration_seconds": 131.2,
    "usage": {"total_tokens": 100},
    "future_field": {"preserved": True},
}


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        self.capture = self.root / "invocation.json"
        self.stub = self.root / "agy stub"
        self.stub.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['STUB_CAPTURE']).write_text(json.dumps({\n"
            " 'args': sys.argv[1:], 'cwd': os.getcwd(), 'stdin': sys.stdin.read()}))\n"
            "sys.stdout.write(pathlib.Path(os.environ['STUB_STDOUT_FILE']).read_text())\n"
            "sys.stderr.write(os.environ.get('STUB_STDERR', ''))\n"
            "sys.exit(int(os.environ.get('STUB_EXIT', '0')))\n"
        )
        self.stub.chmod(0o700)

    def run_wrapper(self, *args, **kwargs):
        return self.run_command(["bash", str(WRAPPER), *args], **kwargs)

    def run_command(self, command, prompt="test prompt", result=None,
                    raw=None, stderr="", agy_exit=0, env_extra=None,
                    stdin=None, test_timeout=10):
        self.capture.unlink(missing_ok=True)
        stdout_file = self.root / "stub-stdout.txt"
        stdout_file.write_text(raw if raw is not None else json.dumps(
            SUCCESS if result is None else result))
        env = dict(os.environ, AGY_BIN=str(self.stub), STUB_CAPTURE=str(self.capture),
                   STUB_STDOUT_FILE=str(stdout_file),
                   STUB_STDERR=stderr, STUB_EXIT=str(agy_exit), TMPDIR=str(self.root))
        env.update(env_extra or {})
        with subprocess.Popen(command, stdin=subprocess.PIPE if stdin is None else stdin,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, cwd=self.root, env=env,
                              start_new_session=True) as child:
            try:
                stdout, stderr = child.communicate(
                    input=prompt if stdin is None else None, timeout=test_timeout)
            except subprocess.TimeoutExpired:
                # Kill cat as well as Bash, so a regression cannot hang the suite
                # by leaving a descendant holding the output pipes open.
                os.killpg(child.pid, signal.SIGKILL)
                child.communicate()
                raise
            proc = subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
        self.assertEqual(list(self.root.glob("agy-run.*")), [], "scratch not cleaned")
        return proc

    def metadata(self, proc):
        self.assertEqual(len(proc.stderr.splitlines()), 1, proc.stderr)
        self.assertTrue(proc.stderr.startswith("agy-run: "), proc.stderr)
        return json.loads(proc.stderr.removeprefix("agy-run: "))

    def invocation(self):
        return json.loads(self.capture.read_text())

    def assert_outcome(self, proc, code, outcome):
        self.assertEqual(proc.returncode, code, proc.stderr + proc.stdout)
        envelope = json.loads(proc.stdout)
        self.assertEqual(envelope["exit_code"], code)
        self.assertEqual(envelope["outcome"], outcome)
        self.assertEqual(envelope["version"], 2)
        return envelope

    def test_default_text_and_metadata(self):
        proc = self.run_wrapper()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "PONG\n")
        self.assertEqual(self.metadata(proc), {
            "outcome": "ok", "exit_code": 0, "agy_exit_code": 0,
            "conversation_id": "test-conversation"})
        invocation = self.invocation()
        args = invocation["args"]
        self.assertEqual(args[args.index("--print-timeout") + 1], "600s")
        self.assertEqual(args[args.index("--output-format") + 1], "json")
        self.assertEqual(invocation["stdin"], "")
        self.assertNotIn("--model", args)
        self.assertNotIn("--effort", args)

    def test_json_compact_preserves_fields_without_raw_duplication(self):
        proc = self.run_wrapper("--json")
        envelope = self.assert_outcome(proc, 0, "ok")
        self.assertEqual(envelope["result"], SUCCESS)
        self.assertNotIn("raw_stdout", envelope)
        self.assertNotIn("stderr", envelope)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(len(proc.stdout.splitlines()), 1)

    def test_include_raw_implies_json(self):
        raw = json.dumps(SUCCESS, indent=2) + "\n"
        proc = self.run_wrapper("--include-raw", raw=raw)
        envelope = self.assert_outcome(proc, 0, "ok")
        self.assertEqual(envelope["raw_stdout"], raw)
        self.assertEqual(envelope["stderr"], "")

    def test_positional_prompt_is_literal_and_preserves_newlines(self):
        prompt = "Quote ' and \"; $(touch INJECTED); `touch INJECTED2`\nlast\n\n"
        proc = self.run_wrapper("--cwd", str(self.project), prompt,
                                prompt="ignored stdin")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        args = self.invocation()["args"]
        self.assertTrue(args[args.index("-p") + 1].endswith(prompt))
        self.assertFalse((self.project / "INJECTED").exists())
        self.assertFalse((self.project / "INJECTED2").exists())

    def test_dash_prefixed_positional_prompt(self):
        proc = self.run_wrapper("--", "--json is literal prompt text")
        self.assertEqual(proc.stdout, "PONG\n")
        self.assertTrue(self.invocation()["args"][-1].endswith(
            "--json is literal prompt text"))

    def test_relative_paths_resolved_before_cwd(self):
        (self.root / "prompt.txt").write_text("file prompt\n\n")
        (self.root / "schema.json").write_text('{"type":"object"}')
        extra = self.root / "extra dir"
        extra.mkdir()
        proc = self.run_wrapper("--cwd", self.project.name,
                                "--prompt-file", "prompt.txt",
                                "--json-schema", "schema.json",
                                "--add-dir", extra.name, prompt="ignored")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        invocation = self.invocation()
        self.assertEqual(invocation["cwd"], str(self.project))
        args = invocation["args"]
        self.assertEqual(args[args.index("--add-dir") + 1], str(extra))
        self.assertEqual(json.loads(args[args.index("--json-schema") + 1]),
                         {"type": "object"})
        self.assertTrue(args[-1].endswith("file prompt\n\n"))

    def test_explicit_stdin(self):
        proc = self.run_wrapper("--prompt-file", "-", prompt="stdin prompt\n\n")
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(self.invocation()["args"][-1].endswith("stdin prompt\n\n"))

    def test_implicit_pipe_preserves_prompt(self):
        prompt = "pipe prompt\nwith another line\n\n"
        proc = self.run_wrapper(prompt=prompt)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.invocation()["args"][-1].endswith(prompt))

    def test_implicit_regular_file_stdin(self):
        prompt = "redirected file prompt\n\n"
        path = self.root / "stdin.txt"
        path.write_text(prompt)
        with path.open() as source:
            proc = self.run_wrapper(stdin=source)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.invocation()["args"][-1].endswith(prompt))

    def test_quoted_heredoc_stdin(self):
        prompt = "literal $(touch INJECTED) and `touch INJECTED2`\n\n"
        proc = self.run_command([
            "bash", "-c", 'exec bash "$1" <<\'PROMPT\'\n' + prompt + "PROMPT\n",
            "heredoc-test", str(WRAPPER)])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.invocation()["args"][-1].endswith(prompt))
        self.assertFalse((self.root / "INJECTED").exists())
        self.assertFalse((self.root / "INJECTED2").exists())

    def test_missing_prompt_with_never_eof_socket_fails_fast(self):
        for args in [(), ("--json",)]:
            with self.subTest(args=args):
                source, peer = socket.socketpair()
                with source, peer:
                    # Keep the peer open and silent until the wrapper exits.
                    proc = self.run_wrapper(*args, stdin=source, test_timeout=2)
                self.assertEqual(proc.returncode, 64)
                if args:
                    metadata = self.assert_outcome(proc, 64, "usage_error")
                else:
                    self.assertEqual(proc.stdout, "")
                    metadata = self.metadata(proc)
                self.assertEqual(metadata["outcome"], "usage_error")
                self.assertIsNone(metadata["agy_exit_code"])
                self.assertIn("prompt", metadata["message"].lower())
                self.assertFalse(self.capture.exists())

    def test_explicit_prompts_ignore_never_eof_socket(self):
        prompt = "explicit prompt\n\n"
        path = self.root / "prompt.txt"
        path.write_text(prompt)
        for args in [(prompt,), ("--prompt-file", str(path))]:
            with self.subTest(args=args):
                source, peer = socket.socketpair()
                with source, peer:
                    proc = self.run_wrapper(*args, stdin=source, test_timeout=2)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertTrue(self.invocation()["args"][-1].endswith(prompt))

    def test_explicit_socket_stdin(self):
        prompt = "explicit socket prompt\n\n"
        source, peer = socket.socketpair()
        with source, peer:
            self.assertEqual(os.write(peer.fileno(), prompt.encode()), len(prompt.encode()))
            peer.close()
            proc = self.run_wrapper("--prompt-file", "-", stdin=source, test_timeout=2)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.invocation()["args"][-1].endswith(prompt))

    def test_missing_prompt_with_character_device_fails_fast(self):
        for path in ["/dev/null", "/dev/zero"]:
            with self.subTest(path=path), open(path) as source:
                proc = self.run_wrapper("--json", stdin=source, test_timeout=2)
                envelope = self.assert_outcome(proc, 64, "usage_error")
                self.assertIn("Supply", envelope["message"])
                self.assertFalse(self.capture.exists())

    def test_tty_stdin_is_rejected(self):
        master, slave = pty.openpty()
        with os.fdopen(master, "rb") as master_file, os.fdopen(slave, "rb") as source:
            for args in [(), ("--prompt-file", "-")]:
                with self.subTest(args=args):
                    proc = self.run_wrapper("--json", *args, stdin=source, test_timeout=2)
                    self.assert_outcome(proc, 64, "usage_error")
                    self.assertFalse(self.capture.exists())

    def test_permissions(self):
        for level, mode in [("none", "plan"), ("files", "accept-edits"),
                            ("commands", "accept-edits")]:
            with self.subTest(level=level):
                proc = self.run_wrapper("--write-level", level)
                self.assertEqual(proc.returncode, 0)
                args = self.invocation()["args"]
                self.assertIn("--sandbox", args)
                self.assertEqual(args[args.index("--mode") + 1], mode)
                self.assertEqual("--dangerously-skip-permissions" in args,
                                 level == "commands")

    def test_resume_model_and_effort_forwarded(self):
        proc = self.run_wrapper("--resume", "known-id", "--model",
                                "gemini-3.1-pro-low", "--effort", "low",
                                result=dict(SUCCESS, conversation_id="known-id"))
        self.assertEqual(proc.returncode, 0)
        args = self.invocation()["args"]
        for option, value in [("--conversation", "known-id"),
                              ("--model", "gemini-3.1-pro-low"), ("--effort", "low")]:
            self.assertEqual(args[args.index(option) + 1], value)
        self.assertNotIn("--continue", args)

    def test_missing_conversation_warning_overrides_success(self):
        warning = 'warning: conversation "not-a-real-id" not found\n'
        # The warning must independently fail even if the result echoes the ID.
        for returned_id in ["new-conversation", "not-a-real-id"]:
            with self.subTest(returned_id=returned_id):
                result = dict(SUCCESS, conversation_id=returned_id)
                proc = self.run_wrapper("--json", "--resume", "not-a-real-id",
                                        result=result, stderr=warning)
                envelope = self.assert_outcome(proc, 12, "agy_error")
                self.assertEqual(envelope["agy_exit_code"], 0)
                self.assertEqual(envelope["result"], result)
                self.assertEqual(envelope["stderr"], warning)
                self.assertIn("conversation not found", envelope["message"])

    def test_resume_id_mismatch_without_warning(self):
        for returned_id in ["new-conversation", "", "known-id-extra", "KNOWN-ID"]:
            with self.subTest(returned_id=returned_id):
                proc = self.run_wrapper("--json", "--resume", "known-id",
                                        result=dict(SUCCESS, conversation_id=returned_id))
                envelope = self.assert_outcome(proc, 12, "agy_error")
                self.assertEqual(envelope["agy_exit_code"], 0)
                self.assertIn("different", envelope["message"])

    def test_failed_resume_suppresses_text_response(self):
        for returned_id, stderr in [
            ("known-id", 'warning: conversation "known-id" not found\n'),
            ("new-conversation", ""),
        ]:
            with self.subTest(returned_id=returned_id):
                proc = self.run_wrapper("--resume", "known-id", stderr=stderr,
                                        result=dict(SUCCESS, conversation_id=returned_id))
                self.assertEqual(proc.returncode, 12)
                self.assertEqual(proc.stdout, "")
                self.assertEqual(self.metadata(proc)["outcome"], "agy_error")

    def test_failed_resume_takes_precedence_over_timeout(self):
        proc = self.run_wrapper("--json", "--resume", "known-id",
                                stderr="print timeout after 1s\n")
        self.assert_outcome(proc, 12, "agy_error")

    def test_valid_resume_allows_unrelated_warning(self):
        proc = self.run_wrapper("--resume", "known-id",
                                result=dict(SUCCESS, conversation_id="known-id"),
                                stderr="warning: optional configuration not found\n")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "PONG\n")
        self.assertEqual(self.metadata(proc)["outcome"], "ok")

    def test_timeout_values(self):
        for timeout in ["0", "1s", "600s", "1m30s", "0.5s", "500ms"]:
            with self.subTest(timeout=timeout):
                proc = self.run_wrapper("--timeout", timeout)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                args = self.invocation()["args"]
                self.assertEqual(args[args.index("--print-timeout") + 1], timeout)

    def test_timeout_diagnostic_overrides_success_and_nonzero(self):
        for agy_exit in [0, 7]:
            with self.subTest(agy_exit=agy_exit):
                proc = self.run_wrapper("--json", result=dict(SUCCESS, response="partial"),
                                        stderr="[agy] print timeout after 1s with turn in progress\n",
                                        agy_exit=agy_exit)
                envelope = self.assert_outcome(proc, 10, "timeout")
                self.assertEqual(envelope["agy_exit_code"], agy_exit)
                self.assertEqual(envelope["result"]["response"], "partial")

    def test_explicit_timeout_status(self):
        for status in ["TIMEOUT", "TIMED_OUT"]:
            with self.subTest(status=status):
                proc = self.run_wrapper("--json", result=dict(SUCCESS, status=status))
                self.assert_outcome(proc, 10, "timeout")

    def test_timeout_with_malformed_output(self):
        proc = self.run_wrapper("--json", raw="partial JSON {",
                                stderr="print timeout after 1s")
        envelope = self.assert_outcome(proc, 10, "timeout")
        self.assertEqual(envelope["raw_stdout"], "partial JSON {")

    def test_default_partial_response_and_timeout_metadata(self):
        proc = self.run_wrapper(result=dict(SUCCESS, response="partial"),
                                stderr="print timeout after 1s\nreturning partial output\n")
        self.assertEqual(proc.returncode, 10)
        self.assertEqual(proc.stdout, "partial\n")
        self.assertEqual(self.metadata(proc)["outcome"], "timeout")

    def test_cli_error_json_preserves_original_diagnostics(self):
        result = dict(SUCCESS, status="ERROR", response="", conversation_id="",
                      error="invalid model")
        proc = self.run_wrapper("--json", result=result,
                                stderr="error: invalid model\n", agy_exit=1)
        envelope = self.assert_outcome(proc, 12, "agy_error")
        self.assertEqual(envelope["agy_exit_code"], 1)
        self.assertIsNone(envelope["conversation_id"])
        self.assertEqual(envelope["stderr"], "error: invalid model\n")
        self.assertEqual(envelope["result"], result)

    def test_default_cli_error_deduplicated(self):
        proc = self.run_wrapper(result=dict(SUCCESS, status="ERROR", response="",
                                           error="invalid model\n"),
                                stderr="error: invalid model\n", agy_exit=1)
        self.assertEqual(proc.returncode, 12)
        self.assertEqual(proc.stdout, "")
        metadata = self.metadata(proc)
        self.assertEqual(metadata["error"], "invalid model\n")
        self.assertNotIn("stderr", metadata)

    def test_incomplete_signals(self):
        for result, stderr in [(dict(SUCCESS, response=" \n"), ""),
                               (dict(SUCCESS, denied_actions=["RunCommand"]), ""),
                               (SUCCESS, "jetski: no output produced")]:
            with self.subTest(result=result, stderr=stderr):
                self.assert_outcome(self.run_wrapper("--json", result=result,
                                                     stderr=stderr), 11, "incomplete")

    def test_structured_error_does_not_break_text_metadata(self):
        error = {"code": "MODEL_ERROR", "detail": "unavailable"}
        proc = self.run_wrapper(result=dict(SUCCESS, status="ERROR", response="",
                                           error=error), stderr="model unavailable\n")
        self.assertEqual(proc.returncode, 12)
        metadata = self.metadata(proc)
        self.assertEqual(metadata["error"], error)
        self.assertEqual(metadata["stderr"], "model unavailable\n")

    def test_refusal_is_transport_success(self):
        proc = self.run_wrapper("--json", result=dict(
            SUCCESS, response="I cannot run the requested command in plan mode."))
        self.assert_outcome(proc, 0, "ok")

    def test_schema_response_is_not_silently_validated(self):
        schema = self.root / "schema.json"
        schema.write_text('{"type":"object"}')
        proc = self.run_wrapper("--json-schema", str(schema), result=dict(
            SUCCESS, response="Here is some prose instead."))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "Here is some prose instead.\n")

    def test_malformed_stdout_preserved(self):
        for raw in ["not JSON\n", "{}\n{}", "[]", "null", ""]:
            with self.subTest(raw=raw):
                envelope = self.assert_outcome(
                    self.run_wrapper("--json", raw=raw), 12, "agy_error")
                self.assertIsNone(envelope["result"])
                self.assertEqual(envelope.get("raw_stdout", ""), raw)
        proc = self.run_wrapper(raw="broken JSON\n")
        self.assertEqual(proc.stdout, "")
        self.assertEqual(self.metadata(proc)["raw_stdout"], "broken JSON\n")

    def test_unexpected_result_fields(self):
        for result in [{}, dict(SUCCESS, status="ERROR"),
                       dict(SUCCESS, response=123), dict(SUCCESS, denied_actions="bad")]:
            with self.subTest(result=result):
                self.assert_outcome(self.run_wrapper("--json", result=result),
                                    12, "agy_error")

    def test_large_output_does_not_hit_argv_limit(self):
        response = "x" * 250000
        proc = self.run_wrapper("--json", result=dict(SUCCESS, response=response))
        envelope = self.assert_outcome(proc, 0, "ok")
        self.assertEqual(envelope["result"]["response"], response)
        self.assertNotIn("raw_stdout", envelope)

    def test_usage_errors_do_not_launch_agy(self):
        cases = [
            ["--cwd"], ["--model", "claude-sonnet-4-6", "--effort", "low"],
            ["--effort", "invalid"], ["--write-level", "invalid"],
            ["--timeout", "-1s"], ["--timeout", "abc"], ["--unknown"],
            ["one", "two"], ["--"], ["--", "one", "two"],
            ["--prompt-file", "-", "positional"],
            ["--prompt-file", "-", "--prompt-file", "-"],
            ["--cwd", "missing"], ["--add-dir", "missing"],
            ["--prompt-file", "missing"], ["--json-schema", "missing"],
        ]
        for args in cases:
            with self.subTest(args=args):
                self.assert_outcome(self.run_wrapper("--json", *args), 64, "usage_error")
                self.assertFalse(self.capture.exists())

    def test_invalid_prompt_inputs(self):
        for prompt in ["", " \n\t", "text\0more", "x" * 200000, "x" * 119999]:
            with self.subTest(size=len(prompt)):
                self.assert_outcome(self.run_wrapper("--json", prompt=prompt),
                                    64, "usage_error")
                self.assertFalse(self.capture.exists())

    def test_invalid_schema_inputs(self):
        schema = self.root / "schema.json"
        for content in ["[1]", "{} {}", "not JSON", '{"large":"' + "x" * 120000 + '"}']:
            with self.subTest(size=len(content)):
                schema.write_text(content)
                self.assert_outcome(self.run_wrapper("--json", "--json-schema", str(schema)),
                                    64, "usage_error")
                self.assertFalse(self.capture.exists())

    def test_default_usage_metadata(self):
        proc = self.run_wrapper("--cwd")
        self.assertEqual(proc.returncode, 64)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(self.metadata(proc)["outcome"], "usage_error")

    def test_missing_binary(self):
        proc = self.run_wrapper("--json", env_extra={"AGY_BIN": str(self.root / "missing")})
        envelope = self.assert_outcome(proc, 12, "agy_error")
        self.assertIsNone(envelope["agy_exit_code"])
        self.assertFalse(self.capture.exists())

    def test_help(self):
        proc = self.run_wrapper("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("600s", proc.stdout)
        self.assertIn("--json", proc.stdout)
        self.assertFalse(self.capture.exists())


if __name__ == "__main__":
    unittest.main()
