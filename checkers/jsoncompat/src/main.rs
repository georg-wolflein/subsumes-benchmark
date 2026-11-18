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

/// The reply to a request, without its time.
fn check(request: &str, options: &SchemaOptions) -> Result<Value, String> {
    let (a, b) = schemas(request)?;
    let read = |schema: &Value| -> Result<SchemaDocument, String> {
        SchemaDocument::from_json_with_options(schema, options).map_err(|e| e.to_string())
    };
    let (a, b) = (read(&a)?, read(&b)?);
    let result = analyze_compat(&a, &b, Role::Serializer).map_err(|e| e.to_string())?;
    Ok(match result {
        CompatibilityResult::Compatible => json!({"answer": true}),
        CompatibilityResult::Incompatible { counterexample, .. } => {
            json!({"answer": false, "message": counterexample.to_string()})
        }
        CompatibilityResult::Unknown { reason } => json!({"answer": null, "message": reason}),
    })
}

fn answer(request: &str, options: &SchemaOptions) -> Value {
    // jsoncompat takes a schema as a parsed value, and the request is parsed into the two.
    // So the clock runs from the request as text to the answer: each schema is parsed once
    // in that time, and nothing else of weight.
    let start = Instant::now();
    let outcome = check(request, options);
    let seconds = start.elapsed().as_secs_f64();
    let mut reply =
        outcome.unwrap_or_else(|message| json!({"failure": "error", "message": message}));
    reply["seconds"] = json!(seconds);
    reply
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
