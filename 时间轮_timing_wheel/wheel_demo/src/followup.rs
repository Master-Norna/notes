//! Bounded three-version experiments for the follow-up article.
use crate::stack::{Item, SlotStack, VecStore};
use std::panic::{catch_unwind, AssertUnwindSafe};

#[derive(Debug, PartialEq, Eq)]
pub struct Trace {
    pub first_poll_at: Option<u64>,
    pub fired: Vec<(&'static str, u64)>,
}

// Catch debug assertions so the example can show the rest of the matrix.
// The step limit also turns a non-progressing wheel into a bounded failure.
macro_rules! simulator {
    ($name:ident, $module:ident) => {
        pub fn $name(elapsed: u64, entries: &[(u64, &'static str)]) -> Result<Trace, String> {
            catch_unwind(AssertUnwindSafe(|| {
                let mut store = VecStore::default();
                let mut wheel = crate::$module::Wheel::<SlotStack>::new();
                assert!(wheel.poll(elapsed, &mut store).is_none());
                for &(when, label) in entries {
                    let key = store.items.len();
                    store.items.push(Item(when, label));
                    wheel.insert(when, key, &mut store).unwrap();
                }
                let mut trace = Trace {
                    first_poll_at: wheel.poll_at(),
                    fired: Vec::new(),
                };
                let mut wake = elapsed;
                for _ in 0..256 {
                    let Some(at) = wheel.poll_at() else {
                        assert_eq!(trace.fired.len(), entries.len());
                        return trace;
                    };
                    wake = wake.max(at); // A driver cannot turn time backwards.
                    if let Some(key) = wheel.poll(wake, &mut store) {
                        trace.fired.push((store.items[key].1, wake));
                    }
                }
                panic!("driver step limit exceeded");
            }))
            .map_err(|payload| {
                if let Some(s) = payload.downcast_ref::<String>() {
                    s.clone()
                } else if let Some(s) = payload.downcast_ref::<&str>() {
                    (*s).to_owned()
                } else {
                    "non-string panic".to_owned()
                }
            })
        }
    };
}

simulator!(original, wheel_buggy);
simulator!(all_levels, wheel_fixed);
simulator!(merged, wheel_merged);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wrapped_top_slot_needs_the_offset() {
        let near = (1 << 30) + 1000;
        let far = (1 << 36) + 1;
        let entries = [(near, "near"), (far, "far")];
        if cfg!(debug_assertions) {
            assert!(original(2, &entries).unwrap_err().contains("assertion"));
        } else {
            let old = original(2, &entries).unwrap();
            assert_eq!(old.first_poll_at, Some(1 << 36));
            assert_eq!(old.fired, vec![("far", far), ("near", (1 << 36) + near)]);
        }
        let expected = Trace {
            first_poll_at: Some(1 << 30),
            fired: vec![("near", near), ("far", far)],
        };
        assert_eq!(all_levels(2, &entries).unwrap(), expected);
        assert_eq!(merged(2, &entries).unwrap(), expected);
    }

    #[test]
    fn both_review_cases_expose_the_all_level_regression() {
        for (a, b, delayed_a) in [(64, 65, 65), (4096, 4160, 8192)] {
            let entries = [(a, "a"), (b, "b")];
            let expected = Trace {
                first_poll_at: Some(a),
                fired: vec![("a", a), ("b", b)],
            };
            assert_eq!(original(0, &entries).unwrap(), expected);
            assert_eq!(merged(0, &entries).unwrap(), expected);
            let wrong = all_levels(0, &entries);
            if cfg!(debug_assertions) && a == 4096 {
                assert!(wrong.unwrap_err().contains("assertion"));
            } else {
                assert_eq!(wrong.unwrap().fired, vec![("b", b), ("a", delayed_a)]);
            }
        }
    }

    #[test]
    fn current_top_slot_is_not_discarded_when_it_is_the_only_one() {
        let far = (1 << 36) + 1;
        let trace = merged(2, &[(far, "far")]).unwrap();
        assert_eq!(trace.first_poll_at, Some(1 << 36));
        assert_eq!(trace.fired, vec![("far", far)]);
    }

    #[test]
    fn merged_cascades_at_every_lower_level_and_later_rotations() {
        // First boundary at each tier, plus later rotations. Check both stack orders.
        for level in 1..=5 {
            let boundary = 1u64 << (6 * level);
            let width_below = 1u64 << (6 * (level - 1));
            for cycle in [1, 2, 63, 64, 65] {
                let a = cycle * boundary;
                let b = a + width_below;
                for entries in [[(a, "a"), (b, "b")], [(b, "b"), (a, "a")]] {
                    let trace = merged(a - 1, &entries).unwrap();
                    assert_eq!(trace.fired, vec![("a", a), ("b", b)]);
                }
            }
        }
    }
}
