//! The adapter for subsumes: answers the runner's requests, one JSON line each.
//!
//! "A accepts every instance of B" is the library's own question, with the two schemas in
//! that order. The library always asserts `format`, so there is nothing to set for it.

use std::io::{self, BufRead, Write};
use std::time::Instant;

use serde_json::{Value, json};
use subsumes::{Checker, Reason, Verdict};

/// The reply without its time.
fn check(a: &str, b: &str, checker: &Checker) -> Result<Value, String> {
    let parse = |text: &str| serde_json::from_str::<Value>(text).map_err(|e| e.to_string());
    let (a, b) = (parse(a)?, parse(b)?);
    Ok(match checker.subsumes(&a, &b).map_err(|e| e.to_string())? {
        Verdict::Yes => json!({"answer": "yes"}),
        Verdict::No { counterexample } => json!({
            "answer": "no",
            "detail": counterexample.to_string(),
            "counterexample": counterexample,
        }),
        // A check that spends its work budget ends here too, and the reason says so.
        Verdict::Unknown { reason } => json!({
            "answer": "unknown",
            "detail": reason.to_string(),
            "reason": kind(&reason),
        }),
    })
}

/// What a report counts the declined tasks by: the keyword that is not supported, or what
/// else ended the check.
fn kind(reason: &Reason) -> String {
    match reason {
        Reason::Budget => "budget".to_owned(),
        Reason::Unrepresentable => "unrepresentable instance".to_owned(),
        // The location is a URI reference whose fragment is a JSON Pointer, and the last
        // token of the pointer names the keyword.
        Reason::Unsupported { location, .. } => {
            let pointer = location.split_once('#').map_or("", |(_, pointer)| pointer);
            match pointer.rsplit_once('/') {
                Some((_, token)) => token.replace("~1", "/").replace("~0", "~"),
                None => "whole schema".to_owned(),
            }
        }
        _ => "other".to_owned(),
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
    let mut reply = outcome.unwrap_or_else(|detail| json!({"answer": "error", "detail": detail}));
    reply["seconds"] = json!(seconds);
    reply
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
