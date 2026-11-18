//! The adapter for subsumes: answers the runner's requests, one JSON line each.
//!
//! "A accepts every instance of B" is the library's own question, with the two schemas in
//! that order. The library always asserts `format`, so there is nothing to set for it.

use std::io::{self, BufRead, Write};
use std::time::Instant;

use serde_json::{Value, json};
use subsumes::{Checker, Reason, Verdict};

/// The two schemas of a request, which holds each as a JSON value.
fn schemas(request: &str) -> Result<(Value, Value), String> {
    let mut request: Value = serde_json::from_str(request).map_err(|e| e.to_string())?;
    let mut schema = |key: &str| {
        let schema = request.get_mut(key).map(Value::take);
        schema.ok_or(format!("no schema for {key}"))
    };
    Ok((schema("a")?, schema("b")?))
}

/// The reply to a request, without its time.
fn check(request: &str, checker: &Checker) -> Result<Value, String> {
    let (a, b) = schemas(request)?;
    Ok(match checker.subsumes(&a, &b).map_err(|e| e.to_string())? {
        Verdict::Yes => json!({"answer": true}),
        Verdict::No { counterexample } => {
            json!({"answer": false, "counterexample": counterexample})
        }
        // A check that spends its work budget ends here too, and the reason says so.
        Verdict::Unknown { reason } => json!({
            "answer": null,
            "reason": kind(&reason),
            "message": reason.to_string(),
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
    // The library takes a schema as a parsed value, and the request is parsed into the two.
    // So the clock runs from the request as text to the answer: each schema is parsed once
    // in that time, and nothing else of weight.
    let start = Instant::now();
    let outcome = check(request, checker);
    let seconds = start.elapsed().as_secs_f64();
    let mut reply =
        outcome.unwrap_or_else(|message| json!({"failure": "error", "message": message}));
    reply["seconds"] = json!(seconds);
    reply
}

fn main() -> io::Result<()> {
    // The default work budget, which is what a user of the library gets, unless the
    // environment sets another: a run that is to find labels may work for longer.
    let checker = match std::env::var("SUBSUMES_BUDGET") {
        Ok(steps) => Checker::new().budget(steps.parse().map_err(io::Error::other)?),
        Err(_) => Checker::new(),
    };
    let mut out = io::stdout().lock();
    writeln!(out, "{}", json!({"ready": true}))?;
    out.flush()?;
    for line in io::stdin().lock().lines() {
        writeln!(out, "{}", answer(&line?, &checker))?;
        out.flush()?;
    }
    Ok(())
}
