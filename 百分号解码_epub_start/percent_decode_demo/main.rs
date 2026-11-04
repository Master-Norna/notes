//! Reproduce the EPUB resource lookup before and after the percent-decode fix.
//!
//! The two handler bodies below are extracted from the upstream sources:
//!   - before: CaramelizedCUDA/epub-start @ ed7e300b, src-tauri/src/protocol/mod.rs
//!   - after:  CaramelizedCUDA/epub-start @ a349b9e1, src-tauri/src/protocol/mod.rs
//! `normalize_entry_path` and the ZIP central-directory lookup mirror
//! src-tauri/src/services/format_service.rs and the archive reader they use.
//!
//! Usage: rustc -O main.rs -o epub_decode_demo && ./epub_decode_demo [--test]

use std::fs;
use std::path::{Component, Path};

struct Case {
    name: &'static str,
    raw: &'static str,
    before: u16,
    after: u16,
}

const CASES: &[Case] = &[
    Case { name: "CJK segments", raw: "book/7/OEBPS/%E5%9B%BE%E7%89%87/%E5%B0%81%E9%9D%A2.png", before: 404, after: 200 },
    Case { name: "space", raw: "book/7/OEBPS/cover%20v2.png", before: 404, after: 200 },
    Case { name: "hash", raw: "book/7/OEBPS/a%23b.png", before: 404, after: 200 },
    Case { name: "question", raw: "book/7/OEBPS/a%3Fb.png", before: 404, after: 200 },
    Case { name: "percent", raw: "book/7/OEBPS/100%25.png", before: 404, after: 200 },
    Case { name: "raw percent", raw: "book/7/OEBPS/100%.png", before: 200, after: 400 },
    Case { name: "encoded dot-dot", raw: "book/7/%2E%2E/secret", before: 404, after: 403 },
    Case { name: "invalid escape", raw: "book/7/OEBPS/%zz.png", before: 404, after: 400 },
    Case { name: "plain path", raw: "book/7/OEBPS/chapter.xhtml", before: 200, after: 200 },
];

fn read_zip_entries(bytes: &[u8]) -> Vec<String> {
    if bytes.len() < 22 {
        return Vec::new();
    }
    let mut eocd = None;
    for i in (0..=bytes.len() - 22).rev() {
        if bytes[i..i + 4] == [0x50, 0x4b, 0x05, 0x06] {
            eocd = Some(i);
            break;
        }
    }
    let Some(eocd) = eocd else { return Vec::new() };
    let total = u16::from_le_bytes([bytes[eocd + 10], bytes[eocd + 11]]) as usize;
    let offset = u32::from_le_bytes([
        bytes[eocd + 16],
        bytes[eocd + 17],
        bytes[eocd + 18],
        bytes[eocd + 19],
    ]) as usize;

    let mut entries = Vec::new();
    let mut p = offset;
    for _ in 0..total {
        if p + 46 > bytes.len() || bytes[p..p + 4] != [0x50, 0x4b, 0x01, 0x02] {
            break;
        }
        let name_len = u16::from_le_bytes([bytes[p + 28], bytes[p + 29]]) as usize;
        let extra_len = u16::from_le_bytes([bytes[p + 30], bytes[p + 31]]) as usize;
        let comment_len = u16::from_le_bytes([bytes[p + 32], bytes[p + 33]]) as usize;
        let name = String::from_utf8_lossy(&bytes[p + 46..p + 46 + name_len]).into_owned();
        entries.push(name);
        p += 46 + name_len + extra_len + comment_len;
    }
    entries
}

fn normalize_entry_path(path: &str) -> Result<String, String> {
    if path.is_empty() || path.contains('\\') || path.starts_with('/') {
        return Err("VALIDATION_ERROR: invalid EPUB entry path".into());
    }

    let mut segments = Vec::new();
    for component in Path::new(path).components() {
        match component {
            Component::Normal(value) => {
                let value = value
                    .to_str()
                    .ok_or_else(|| "VALIDATION_ERROR: invalid EPUB entry encoding".to_string())?;
                if value.is_empty() {
                    return Err("VALIDATION_ERROR: invalid EPUB entry path".into());
                }
                segments.push(value);
            }
            Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err("VALIDATION_ERROR: EPUB entry traversal rejected".into());
            }
        }
    }

    if segments.is_empty() {
        Err("VALIDATION_ERROR: invalid EPUB entry path".into())
    } else {
        Ok(segments.join("/"))
    }
}

fn decode_uri_path(path: &str) -> Result<String, String> {
    let bytes = path.as_bytes();
    let mut decoded = Vec::with_capacity(bytes.len());
    let mut index = 0usize;
    while index < bytes.len() {
        if bytes[index] == b'%' {
            if index + 2 >= bytes.len() {
                return Err("VALIDATION_ERROR: invalid percent encoding in resource URI".into());
            }
            let high = decode_hex_digit(bytes[index + 1])?;
            let low = decode_hex_digit(bytes[index + 2])?;
            decoded.push((high << 4) | low);
            index += 3;
        } else {
            decoded.push(bytes[index]);
            index += 1;
        }
    }
    String::from_utf8(decoded)
        .map_err(|_| "VALIDATION_ERROR: invalid percent encoding in resource URI".into())
}

fn decode_hex_digit(value: u8) -> Result<u8, String> {
    match value {
        b'0'..=b'9' => Ok(value - b'0'),
        b'a'..=b'f' => Ok(value - b'a' + 10),
        b'A'..=b'F' => Ok(value - b'A' + 10),
        _ => Err("VALIDATION_ERROR: invalid percent encoding in resource URI".into()),
    }
}

fn lookup<'a>(entries: &'a [String], path: &str) -> Option<&'a str> {
    entries.iter().find(|entry| entry.as_str() == path).map(String::as_str)
}

fn handle_before(raw: &str, entries: &[String]) -> Result<String, (u16, String)> {
    let segments = raw.splitn(3, '/').collect::<Vec<_>>();
    if segments.len() != 3 || segments[0] != "book" || segments[1].is_empty() {
        return Err((400, "invalid EPUB resource URI".into()));
    }
    let entry_path = normalize_entry_path(segments[2]).map_err(|message| (403, message))?;
    match lookup(entries, &entry_path) {
        Some(entry) => Ok(entry.to_string()),
        None => Err((404, format!("BOOK_RESOURCE_NOT_FOUND: {entry_path}"))),
    }
}

fn handle_after(raw: &str, entries: &[String]) -> Result<String, (u16, String)> {
    let path = decode_uri_path(raw).map_err(|message| (400, message))?;
    let segments = path.splitn(3, '/').collect::<Vec<_>>();
    if segments.len() != 3 || segments[0] != "book" || segments[1].is_empty() {
        return Err((400, "invalid EPUB resource URI".into()));
    }
    let entry_path = normalize_entry_path(segments[2]).map_err(|message| (403, message))?;
    match lookup(entries, &entry_path) {
        Some(entry) => Ok(entry.to_string()),
        None => Err((404, format!("BOOK_RESOURCE_NOT_FOUND: {entry_path}"))),
    }
}

fn status(result: &Result<String, (u16, String)>) -> u16 {
    match result {
        Ok(_) => 200,
        Err((code, _)) => *code,
    }
}

fn main() {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let test = args.iter().any(|arg| arg == "--test");
    let file = args.iter().find(|arg| !arg.starts_with("--")).map(String::as_str).unwrap_or("sample.epub");
    let bytes = fs::read(file).unwrap_or_else(|error| {
        eprintln!("cannot read {file}: {error}; run `python make_sample.py` first");
        std::process::exit(2);
    });
    let entries = read_zip_entries(&bytes);

    println!("sample: {file} ({} entries)", entries.len());
    for entry in &entries {
        println!("  {entry}");
    }
    println!();
    println!("{:<18} {:<52} {:>6} {:>6}", "case", "raw request path", "before", "after");
    let mut failures = 0;
    let mut before_counts = std::collections::BTreeMap::new();
    let mut after_counts = std::collections::BTreeMap::new();
    for case in CASES {
        let before = handle_before(case.raw, &entries);
        let after = handle_after(case.raw, &entries);
        let before_status = status(&before);
        let after_status = status(&after);
        *before_counts.entry(before_status).or_insert(0) += 1;
        *after_counts.entry(after_status).or_insert(0) += 1;
        println!(
            "{:<18} {:<52} {:>6} {:>6}",
            case.name, case.raw, before_status, after_status
        );
        if before_status != case.before || after_status != case.after {
            failures += 1;
            eprintln!(
                "  MISMATCH {}: expected {}/{}, got {}/{}\n    before: {}\n    after:  {}",
                case.name,
                case.before,
                case.after,
                before_status,
                after_status,
                describe(&before),
                describe(&after)
            );
        }
    }
    println!();
    println!("before status counts: {before_counts:?}");
    println!("after  status counts: {after_counts:?}");
    println!("cases: {}  mismatches: {}", CASES.len(), failures);
    if test && failures > 0 {
        std::process::exit(1);
    }
}

fn describe(result: &Result<String, (u16, String)>) -> String {
    match result {
        Ok(entry) => format!("200 {entry}"),
        Err((code, message)) => format!("{code} {message}"),
    }
}
