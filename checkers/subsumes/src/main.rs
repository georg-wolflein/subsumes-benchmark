//! The adapter for subsumes: answers the runner's requests, one JSON line each.
//!
//! "A accepts every instance of B" is the library's own question, with the two schemas in
//! that order. The library always asserts `format`, so there is nothing to set for it.

use std::io::{self, BufRead, Write};
use std::time::Instant;

use serde_json::{Value, json};
use subsumes::{Checker, Verdict};

/// The answer and what there is to say about it.
fn check(a: &str, b: &str, checker: &Checker) -> Result<(&'static str, Option<String>), String> {
    let parse = |text: &str| serde_json::from_str::<Value>(text).map_err(|e| e.to_string());
    let (a, b) = (parse(a)?, parse(b)?);
    match checker.subsumes(&a, &b).map_err(|e| e.to_string())? {
        Verdict::Yes => Ok(("yes", None)),
        Verdict::No { counterexample } => Ok(("no", Some(counterexample.to_string()))),
        // A check that spends its work budget ends here too, and the reason says so.
        Verdict::Unknown { reason } => Ok(("unknown", Some(reason.to_string()))),
    }
}

fn answer(request: &str, checker: &Checker) -> Value {
    let read = |request: &Value, key: &str| -> Result<String, String> {
        let path = request[key].as_str().ok_or(format!("no path for {key}"))?;
        std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))
    };
    let texts = serde_json::from_str::<Value>(request)
        .map_err(|e| e.to_string())
        .and_then(|request| Ok((read(&request, "a")?, read(&request, "b")?)));
    let (a, b) = match texts {
        Ok(texts) => texts,
        Err(detail) => return json!({"answer": "error", "detail": detail}),
    };
    // The clock runs from the schemas as text to the answer.
    let start = Instant::now();
    let outcome = check(&a, &b, checker);
    let seconds = start.elapsed().as_secs_f64();
    match outcome {
        Ok((answer, detail)) => json!({"answer": answer, "seconds": seconds, "detail": detail}),
        Err(detail) => json!({"answer": "error", "seconds": seconds, "detail": detail}),
    }
}

fn main() -> io::Result<()> {
    // The default work budget, which is what a user of the library gets.
    let checker = Checker::new();
    let mut out = io::stdout().lock();
    writeln!(out, "{}", json!({"ready": true}))?;
    out.flush()?;
    for line in io::stdin().lock().lines() {
        writeln!(out, "{}", answer(&line?, &checker))?;
        out.flush()?;
    }
    Ok(())
}
