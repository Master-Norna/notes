# Independent input-conversion probe; this does not call datetime-diff.
# Expected records are hand specified, not taken from either conversion path.
def expected-record [year: int, fractional: int = 0] {
    {
        year: $year, month: 2, day: 29
        hour: (if $fractional == 0 { 0 } else { 23 })
        minute: (if $fractional == 0 { 0 } else { 59 })
        second: (if $fractional == 0 { 0 } else { 59 })
        millisecond: $fractional, microsecond: $fractional, nanosecond: $fractional
        timezone: '+00:00'
    }
}

[
    {input: '2000-02-29T00:00:00Z', expected: (expected-record 2000)}
    {input: '2000-02-29T23:59:59.999999999Z', expected: (expected-record 2000 999)}
    {input: '2400-02-29T00:00:00Z', expected: (expected-record 2400)}
    {input: '2024-02-29T00:00:00Z', expected: (expected-record 2024)}
] | each {|case|
    let actual = ($case.input | into datetime | date to-timezone utc | into record)
    let explicit = ($case.input | into datetime --format '%+' | date to-timezone utc | into record)
    {
        input: $case.input
        expected_utc: $case.expected
        default_actual_utc: $actual
        explicit_rfc3339_actual_utc: $explicit
        default_matches_expected: ($actual == $case.expected)
        explicit_matches_expected: ($explicit == $case.expected)
        observation: (if $actual == $case.expected { 'matches_expected' } else { 'known_default_parser_mismatch' })
    }
} | to json --raw
