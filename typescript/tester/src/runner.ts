/**
 * SOL26 Tester - Test execution engine.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { spawnSync } from "node:child_process";

import {
  CategoryReport,
  TestCaseDefinition,
  TestCaseReport,
  TestCaseType,
  TestResult,
  UnexecutedReason,
  UnexecutedReasonCode,
} from "./models.js";

// ------------------------------------------------------------------
// Paths to external tools
// ------------------------------------------------------------------

const INT_DIR = "/int";
const SOLINT_SCRIPT = path.join("/int", "src", "solint.py");

const INTERPRETER_CMD = process.env["SOL_INTERPRETER"] ?? "python";
const INTERPRETER_ARGS = process.env["SOL_INTERPRETER_ARGS"]?.split(" ") ?? [SOLINT_SCRIPT];
const SOL2XML_CMD = process.env["SOL2XML"] ?? "sol2xml";

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function runProcess(
  cmd: string,
  args: string[],
  stdinFile: string | null,
  cwd?: string,
  timeoutMs = 10_000
): { code: number; stdout: string; stderr: string } {
  const stdinContent = stdinFile ? fs.readFileSync(stdinFile) : Buffer.alloc(0);

  const result = spawnSync(cmd, args, {
    input: stdinContent,
    timeout: timeoutMs,
    maxBuffer: 10 * 1024 * 1024,
    cwd,
    env: {
      ...process.env,
      PYTHONPATH: path.join(INT_DIR, "src"),
    },
  });

  const stdout = result.stdout?.toString("utf-8") ?? "";
  let stderr = result.stderr?.toString("utf-8") ?? "";

  if (result.error) {
    stderr += (stderr ? "\n" : "") + `spawn error: ${result.error.message}`;
  }

  return {
    code: result.status ?? 1,
    stdout,
    stderr,
  };
}

function runDiff(actualOutput: string, expectedFile: string): string | null {
  const tmpFile = path.join(os.tmpdir(), `sol26_actual_${process.pid}.txt`);
  fs.writeFileSync(tmpFile, actualOutput, "utf-8");

  try {
    const result = spawnSync("diff", [expectedFile, tmpFile], {
      maxBuffer: 1024 * 1024,
    });
    if (result.status === 0) return null;
    return result.stdout?.toString("utf-8") ?? "";
  } finally {
    fs.unlinkSync(tmpFile);
  }
}

function writeTempSource(content: string, ext: string): string {
  const tmpFile = path.join(os.tmpdir(), `sol26_src_${process.pid}.${ext}`);
  fs.writeFileSync(tmpFile, content, "utf-8");
  return tmpFile;
}

/** Extract source code from a .test file (everything after the first blank line). */
function extractSource(raw: string): string {
  const idx = raw.indexOf("\n\n");
  if (idx === -1) return raw;
  return raw.slice(idx + 2);
}

// ------------------------------------------------------------------
// Single test execution
// ------------------------------------------------------------------

function runSingleTest(test: TestCaseDefinition): TestCaseReport | UnexecutedReason {
  let xmlPath: string | null = null;
  let tempSolFile: string | null = null;

  let parserCode: number | null = null;
  let parserStdout: string | null = null;
  let parserStderr: string | null = null;

  try {
    // ── Phase 1: Parser (PARSE_ONLY or COMBINED) ──────────────────
    if (test.test_type === TestCaseType.PARSE_ONLY || test.test_type === TestCaseType.COMBINED) {
      const source = fs.readFileSync(test.test_source_path, "utf-8");
      const sourceOnly = extractSource(source);
      tempSolFile = writeTempSource(sourceOnly, "sol");

      const parserResult = runProcess(SOL2XML_CMD, [tempSolFile], null);
      parserCode = parserResult.code;
      parserStdout = parserResult.stdout;
      parserStderr = parserResult.stderr;

      const allowedCodes = test.expected_parser_exit_codes ?? [];
      if (!allowedCodes.includes(parserCode)) {
        return new TestCaseReport(
          TestResult.UNEXPECTED_PARSER_EXIT_CODE,
          parserCode,
          null,
          parserStdout,
          parserStderr
        );
      }

      // PARSE_ONLY ends here
      if (test.test_type === TestCaseType.PARSE_ONLY) {
        return new TestCaseReport(TestResult.PASSED, parserCode, null, parserStdout, parserStderr);
      }

      // COMBINED: ak parser vrátil non-zero (ale allowed) → koniec
      if (parserCode !== 0) {
        return new TestCaseReport(TestResult.PASSED, parserCode, null, parserStdout, parserStderr);
      }

      // Parser vrátil 0 → XML je v parserStdout
      xmlPath = writeTempSource(parserStdout, "xml");
    } else {
      // EXECUTE_ONLY — zdroj je už XML
      const source = fs.readFileSync(test.test_source_path, "utf-8");
      const sourceOnly = extractSource(source);
      xmlPath = writeTempSource(sourceOnly, "xml");
    }

    // ── Phase 2: Interpreter ──────────────────────────────────────
    if (xmlPath === null) {
      return new UnexecutedReason(UnexecutedReasonCode.OTHER, "No XML file to interpret");
    }

    console.error(
      `[DEBUG] Running interpreter: ${INTERPRETER_CMD} ${[...INTERPRETER_ARGS, xmlPath].join(" ")}`
    );

    const interpResult = runProcess(
      INTERPRETER_CMD,
      [...INTERPRETER_ARGS, xmlPath],
      test.stdin_file,
      "/int/src"
    );

    console.error(
      `[DEBUG] Interpreter result: code=${interpResult.code}, stderr="${interpResult.stderr.substring(0, 200)}"`
    );

    const interpCode = interpResult.code;
    const interpStdout = interpResult.stdout;
    const interpStderr = interpResult.stderr;

    const allowedInterpCodes = test.expected_interpreter_exit_codes ?? [];
    if (!allowedInterpCodes.includes(interpCode)) {
      return new TestCaseReport(
        TestResult.UNEXPECTED_INTERPRETER_EXIT_CODE,
        parserCode,
        interpCode,
        parserStdout,
        parserStderr,
        interpStdout,
        interpStderr
      );
    }

    // ── Phase 3: Diff ─────────────────────────────────────────────
    let diffOutput: string | null = null;
    if (test.expected_stdout_file !== null && interpCode === 0) {
      diffOutput = runDiff(interpStdout, test.expected_stdout_file);
      if (diffOutput !== null) {
        return new TestCaseReport(
          TestResult.INTERPRETER_RESULT_DIFFERS,
          parserCode,
          interpCode,
          parserStdout,
          parserStderr,
          interpStdout,
          interpStderr,
          diffOutput
        );
      }
    }

    return new TestCaseReport(
      TestResult.PASSED,
      parserCode,
      interpCode,
      parserStdout,
      parserStderr,
      interpStdout,
      interpStderr,
      diffOutput
    );
  } finally {
    if (tempSolFile && fs.existsSync(tempSolFile)) fs.unlinkSync(tempSolFile);
    if (xmlPath && fs.existsSync(xmlPath) && test.test_type !== TestCaseType.EXECUTE_ONLY) {
      fs.unlinkSync(xmlPath);
    }
  }
}

// ------------------------------------------------------------------
// Main export
// ------------------------------------------------------------------

export async function runTests(
  tests: TestCaseDefinition[]
): Promise<Record<string, CategoryReport>> {
  const categoryMap: Record<
    string,
    { total: number; passed: number; results: Record<string, TestCaseReport> }
  > = {};

  for (const test of tests) {
    if (!categoryMap[test.category]) {
      categoryMap[test.category] = { total: 0, passed: 0, results: {} };
    }
    const cat = categoryMap[test.category]!;

    cat.total += test.points;

    const reportOrReason = runSingleTest(test);

    if (reportOrReason instanceof TestCaseReport) {
      cat.results[test.name] = reportOrReason;
      if (reportOrReason.result === TestResult.PASSED) {
        cat.passed += test.points;
      }
    }
  }

  const result: Record<string, CategoryReport> = {};
  for (const [cat, data] of Object.entries(categoryMap)) {
    result[cat] = new CategoryReport(data.total, data.passed, data.results);
  }
  return result;
}
