/**
 * SOL26 Tester - Test case discovery and parsing.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import {
  TestCaseDefinition,
  TestCaseType,
  UnexecutedReason,
  UnexecutedReasonCode,
} from "./models.js";

interface CliFilterArgs {
  tests_dir: string;
  recursive: boolean;
  include: string[] | null;
  include_category: string[] | null;
  include_test: string[] | null;
  exclude: string[] | null;
  exclude_category: string[] | null;
  exclude_test: string[] | null;
  regex_filters: boolean;
}

export interface LoadResult {
  tests: TestCaseDefinition[];
  unexecuted: Record<string, UnexecutedReason>;
}

// ------------------------------------------------------------------
// Discovery
// ------------------------------------------------------------------

function findTestFiles(dir: string, recursive: boolean): string[] {
  const results: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory() && recursive) {
      results.push(...findTestFiles(fullPath, recursive));
    } else if (entry.isFile() && entry.name.endsWith(".test")) {
      results.push(fullPath);
    }
  }
  return results;
}

// ------------------------------------------------------------------
// Parsing a single .test file
// ------------------------------------------------------------------

function parseTestFile(
  filePath: string
): TestCaseDefinition | UnexecutedReason {
  const name = path.basename(filePath, ".test");
  const dir = path.dirname(filePath);
  const raw = fs.readFileSync(filePath, "utf-8");
  const lines = raw.split("\n");

  // Find the blank line separating header from source
  const blankIdx = lines.findIndex((l) => l.trim() === "");
  if (blankIdx === -1) {
    return new UnexecutedReason(
      UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE,
      "No blank line separating header from source code"
    );
  }

  const headerLines = lines.slice(0, blankIdx);

  let category: string | null = null;
  let description: string | null = null;
  let points = 1;
  const compilerCodes: number[] = [];
  const interpreterCodes: number[] = [];

  for (const line of headerLines) {
    if (line.startsWith("+++")) {
      category = line.slice(3).trim();
    } else if (line.startsWith("***")) {
      description = line.slice(3).trim();
    } else if (line.startsWith("!C!")) {
      const code = parseInt(line.slice(3).trim(), 10);
      if (!isNaN(code)) compilerCodes.push(code);
    } else if (line.startsWith("!I!")) {
      const code = parseInt(line.slice(3).trim(), 10);
      if (!isNaN(code)) interpreterCodes.push(code);
    } else if (/^\d+$/.test(line.trim())) {
      points = parseInt(line.trim(), 10);
    }
  }

  if (category === null) {
    return new UnexecutedReason(
      UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE,
      "Missing category (+++ line)"
    );
  }

  // Determine test type
  const hasCompiler = compilerCodes.length > 0;
  const hasInterpreter = interpreterCodes.length > 0;

  let testType: TestCaseType;
  if (hasCompiler && !hasInterpreter) {
    testType = TestCaseType.PARSE_ONLY;
  } else if (!hasCompiler && hasInterpreter) {
    testType = TestCaseType.EXECUTE_ONLY;
  } else if (hasCompiler && hasInterpreter) {
    testType = TestCaseType.COMBINED;
  } else {
    return new UnexecutedReason(
      UnexecutedReasonCode.CANNOT_DETERMINE_TYPE,
      "Cannot determine test type: no !C! or !I! codes"
    );
  }

  // Check companion files
  const stdinPath = path.join(dir, `${name}.in`);
  const stdoutPath = path.join(dir, `${name}.out`);

  try {
    return new TestCaseDefinition({
      name,
      test_source_path: filePath,
      stdin_file: fs.existsSync(stdinPath) ? stdinPath : null,
      expected_stdout_file: fs.existsSync(stdoutPath) ? stdoutPath : null,
      test_type: testType,
      description,
      category,
      points,
      expected_parser_exit_codes: hasCompiler ? compilerCodes : null,
      expected_interpreter_exit_codes: hasInterpreter ? interpreterCodes : null,
    });
  } catch (e: unknown) {
    return new UnexecutedReason(
      UnexecutedReasonCode.MALFORMED_TEST_CASE_FILE,
      e instanceof Error ? e.message : String(e)
    );
  }
}

// ------------------------------------------------------------------
// Filtering
// ------------------------------------------------------------------

function makeMatchers(
  patterns: string[] | null,
  useRegex: boolean
): ((s: string) => boolean)[] {
  if (!patterns) return [];
  return patterns.map((p) => {
    const trimmed = p.trim();
    if (useRegex) {
      const re = new RegExp(trimmed);
      return (s: string) => re.test(s);
    }
    return (s: string) => s === trimmed;
  });
}

function shouldInclude(
  test: TestCaseDefinition,
  args: CliFilterArgs
): boolean {
  const useRegex = args.regex_filters;

  // Include matchers — if any defined, test must match at least one
  const includeNameMatchers = makeMatchers(args.include, useRegex);
  const includeCatMatchers = makeMatchers(args.include_category, useRegex);
  const includeTestMatchers = makeMatchers(args.include_test, useRegex);

  // Exclude matchers — test must not match any
  const excludeNameMatchers = makeMatchers(args.exclude, useRegex);
  const excludeCatMatchers = makeMatchers(args.exclude_category, useRegex);
  const excludeTestMatchers = makeMatchers(args.exclude_test, useRegex);

  // Check include (name or category)
  const hasIncludeFilter =
    (args.include?.length ?? 0) > 0 ||
    (args.include_category?.length ?? 0) > 0 ||
    (args.include_test?.length ?? 0) > 0;

  if (hasIncludeFilter) {
    const nameMatches =
      includeNameMatchers.some((m) => m(test.name)) ||
      includeNameMatchers.some((m) => m(test.category));
    const catMatches = includeCatMatchers.some((m) => m(test.category));
    const testMatches = includeTestMatchers.some((m) => m(test.name));

    if (!nameMatches && !catMatches && !testMatches) return false;
  }

  // Check exclude
  const nameExcluded =
    excludeNameMatchers.some((m) => m(test.name)) ||
    excludeNameMatchers.some((m) => m(test.category));
  const catExcluded = excludeCatMatchers.some((m) => m(test.category));
  const testExcluded = excludeTestMatchers.some((m) => m(test.name));

  if (nameExcluded || catExcluded || testExcluded) return false;

  return true;
}

// ------------------------------------------------------------------
// Main export
// ------------------------------------------------------------------

export function loadTests(args: CliFilterArgs): LoadResult {
  const files = findTestFiles(args.tests_dir, args.recursive);
  const tests: TestCaseDefinition[] = [];
  const unexecuted: Record<string, UnexecutedReason> = {};

  for (const file of files) {
    const name = path.basename(file, ".test");
    const result = parseTestFile(file);

    if (result instanceof TestCaseDefinition) {
      if (shouldInclude(result, args)) {
        tests.push(result);
      } else {
        unexecuted[name] = new UnexecutedReason(UnexecutedReasonCode.FILTERED_OUT);
      }
    } else {
      // UnexecutedReason
      unexecuted[name] = result;
    }
  }

  return { tests, unexecuted };
}
