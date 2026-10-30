# The algorithm lives ONLY in the unmodified upstream files.
# Namespaced modules avoid command-name collisions; @example stays intact.
module before {
    export use upstream/before/mod.nu datetime-diff
}
module draft {
    export use upstream/draft/mod.nu datetime-diff
}
module after {
    export use upstream/after/mod.nu datetime-diff
}
use before
use draft
use after

def capture [version: string, later: datetime, earlier: datetime] {
    try {
        let result = match $version {
            before => { before datetime-diff $later $earlier }
            draft => { draft datetime-diff $later $earlier }
            after => { after datetime-diff $later $earlier }
        }
        {ok: true, result: $result}
    } catch {|err| {ok: false, error: $err.msg} }
}

# An input JSON array of {id, earlier, later}; ISO strings carry explicit offsets.
# Conversion happens outside capture, so a parser failure cannot masquerade as
# a datetime-diff rejection. Also export UTC records to check parser fidelity.
# Explicit RFC3339 parsing isolates the dt algorithm from the default dtparse
# path, which in Nu 0.116.1 changes 2000/2400-02-29 into Feb 28 (see README).
# This is input preparation, NOT a change to any upstream datetime-diff source.
def main [input: path] {
    open --raw $input | from json | each {|case|
        let earlier = ($case.earlier | into datetime --format '%+')
        let later = ($case.later | into datetime --format '%+')
        {
            id: $case.id
            earlier_utc: ($earlier | date to-timezone utc | into record)
            later_utc: ($later | date to-timezone utc | into record)
            before: (capture before $later $earlier)
            draft: (capture draft $later $earlier)
            after: (capture after $later $earlier)
        }
    } | to json --raw
}
