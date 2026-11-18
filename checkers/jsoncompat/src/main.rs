//! The adapter for jsoncompat: answers the runner's requests, one JSON line each.
//!
//! "A accepts every instance of B" is jsoncompat's serializer role with A as the old schema
//! and B as the new one: every value the new schema produces must be accepted by the old.

use std::io::{self, BufRead, Write};
use std::time::Instant;

use jsoncompat::{CompatibilityResult, Role, SchemaDocument, SchemaOptions, analyze_compat};
use serde_json::{Value, json};

/// The two schemas of a request, which holds each as a JSON value.
fn schemas(request: &str) -> Result<(Value, Value), String> {
    let mut request: Value = serde_json::from_str(request).map_err(|e| e.to_string())?;
    let mut schema = |key: &str| {
        let schema = request.get_mut(key).map(Value::take);
        schema.ok_or(format!("no schema for {key}"))
    };
    Ok((schema("a")?, schema("b")?))
}

/// The answer to a request and what there is to say about it.
fn check(request: &str, options: &SchemaOptions) -> Result<(&'static str, Option<String>), String> {
    let (a, b) = schemas(request)?;
    let read = |schema: &Value| -> Result<SchemaDocument, String> {
        SchemaDocument::from_json_with_options(schema, options).map_err(|e| e.to_string())
    };
    let (a, b) = (read(&a)?, read(&b)?);
    match analyze_compat(&a, &b, Role::Serializer).map_err(|e| e.to_string())? {
        CompatibilityResult::Compatible => Ok(("yes", None)),
        CompatibilityResult::Incompatible { counterexample, .. } => {
            Ok(("no", Some(counterexample.to_string())))
        }
        CompatibilityResult::Unknown { reason } => Ok(("unknown", Some(reason))),
    }
}

fn answer(request: &str, options: &SchemaOptions) -> Value {
    // jsoncompat takes a schema as a parsed value, and the request is parsed into the two.
    // So the clock runs from the request as text to the answer: each schema is parsed once
    // in that time, and nothing else of weight.
    let start = Instant::now();
    let outcome = check(request, options);
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
