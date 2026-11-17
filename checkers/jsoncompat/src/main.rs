//! The adapter for jsoncompat: answers the runner's requests, one JSON line each.
//!
//! "A accepts every instance of B" is jsoncompat's serializer role with A as the old schema
//! and B as the new one: every value the new schema produces must be accepted by the old.

use std::io::{self, BufRead, Write};
use std::time::Instant;

use jsoncompat::{CompatibilityResult, Role, SchemaDocument, SchemaOptions, analyze_compat};
use serde_json::{Value, json};

/// The answer and what there is to say about it.
fn check(
    a: &str,
    b: &str,
    options: &SchemaOptions,
) -> Result<(&'static str, Option<String>), String> {
    let parse = |text: &str| -> Result<SchemaDocument, String> {
        let raw: Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
        SchemaDocument::from_json_with_options(&raw, options).map_err(|e| e.to_string())
    };
    let (a, b) = (parse(a)?, parse(b)?);
    match analyze_compat(&a, &b, Role::Serializer).map_err(|e| e.to_string())? {
        CompatibilityResult::Compatible => Ok(("yes", None)),
        CompatibilityResult::Incompatible { counterexample, .. } => {
            Ok(("no", Some(counterexample.to_string())))
        }
        CompatibilityResult::Unknown { reason } => Ok(("unknown", Some(reason))),
    }
}

fn answer(request: &str, options: &SchemaOptions) -> Value {
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
    let outcome = check(&a, &b, options);
    let seconds = start.elapsed().as_secs_f64();
    match outcome {
        Ok((answer, detail)) => json!({"answer": answer, "seconds": seconds, "detail": detail}),
        Err(detail) => json!({"answer": "error", "seconds": seconds, "detail": detail}),
    }
}

fn main() -> io::Result<()> {
    // The corpus's labels hold with `format` asserted.
    let options = SchemaOptions {
        assert_formats: Some(true),
        ..SchemaOptions::default()
    };
    let mut out = io::stdout().lock();
    writeln!(out, "{}", json!({"ready": true}))?;
    out.flush()?;
    for line in io::stdin().lock().lines() {
        writeln!(out, "{}", answer(&line?, &options))?;
        out.flush()?;
    }
    Ok(())
}
