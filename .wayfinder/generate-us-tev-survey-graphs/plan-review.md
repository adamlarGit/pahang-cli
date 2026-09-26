# Engineering Review — US+TEV Survey Graph Generation Plan (v2)

**Reviewer**: Lead engineer  
**Date**: 26 Sep 2026 (re-review after revisions)  
**Artifacts reviewed**: [map.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/generate-us-tev-survey-graphs/map.md), [spec.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/generate-us-tev-survey-graphs/spec.md), all five ticket files, [utility_actions.py](file:///C:/Users/ADAM/Desktop/pahang-cli/src/utility_actions.py), [CONTEXT.md](file:///C:/Users/ADAM/Desktop/pahang-cli/CONTEXT.md)

---

## Overall Verdict

**This plan is ready for implementation.** Every critical gap from the v1 review has been addressed. The remaining items below are minor nits — none of them would block or derail an implementing agent.

---

## Resolution Status of v1 Issues

| # | v1 Issue | Status | Notes |
|---|----------|--------|-------|
| 1 | `survey_summary.js` schema unspecified | ✅ **Resolved** | Spec Decision 2.1 now has concrete JS variable name, top-level keys, `raw_decode` parsing strategy, and Python traversal pseudocode |
| 2 | `measurement_metadata.js` schema unspecified | ✅ **Resolved** | Spec Decision 2.2 now shows the JS variable, `measurement_fields[0]["fields"]` path, and literal `$`-prefixed fieldnames |
| 3 | Option C rendering has no implementation path | ✅ **Resolved** | Spec Decision 3 now cross-references exact functions with line numbers: `find_chrome_executable()`, `SurveyHttpServer`, `render_prpd_option_c_image()`, `is_blank_or_invalid_image()` |
| 4 | Option B rendering has no implementation path | ✅ **Resolved** | Spec Decision 4 now cross-references `decode_tev_event_data()`, `decode_ultrasonic_phase_plot()`, `generate_prpd_figure()` with line numbers and struct format |
| 5 | Station/month selection flow unclear | ✅ **Resolved** | Spec, map, and ticket #003 all now state "Station → Month → Date" drill-down explicitly |
| 6 | Zero-measurement survey handling | ✅ **Resolved** | Ticket #001 returns empty list. Ticket #002 logs `[WARN]` and continues. Map D9 codifies policy |
| 7 | Multi-date checklist merge behavior | ✅ **Resolved** | Map D10 defines single merged checklist with `[{date_str}]` prefix, matching Full Report pattern |
| 8 | Batch error isolation policy | ✅ **Resolved** | Map D9 and ticket #002 codify `SubstationIsolatedBatchResiliencePolicy` with consolidated summary |
| 9 | Output path not consumed by QR | ✅ **Resolved** | Map D6 and spec Decision 8 now explicitly call this out as a known limitation |
| 10 | Ticket #004 is a grab-bag | ✅ **Resolved** | Split into ticket #004 (script refactor) and ticket #005 (ADR + CONTEXT.md + E2E regression) |
| 11 | No ADR | ✅ **Resolved** | Ticket #005 records `docs/adr/0006-us-tev-survey-graph-generation-workflow.md` |
| 12 | GitHub Issues not created | ⬜ Deferred | Still `[Local Draft]` — should be created before ticket #001 starts |
| 13 | Menu position unspecified | ✅ **Resolved** | Position #9 (index 8) after "Rename FLIR raw files numbering" — map D7 |
| 14 | Test fixture data source unclear | ✅ **Resolved** | Ticket #001 specifies synthetic fixtures built in `tmp_path` using patterns from `tests/test_prpd_generator.py` |

---

## New Observations (Minor)

### N1. `UtilityAction` constructor signature mismatch

Ticket #003 line 37 shows the registration as:
```python
UtilityAction("Generate US+TEV survey graphs", _load_generate_us_tev_graphs_runner),
```

The actual `UtilityAction` in [utility_actions.py](file:///C:/Users/ADAM/Desktop/pahang-cli/src/utility_actions.py) uses positional args `(label, _runner_factory)` where `_runner_factory` is `Callable[[], Callable[[], object]]` — a zero-arg factory returning a zero-arg runner. The ticket's snippet matches this pattern (factory name `_load_...`), which is correct. But the handler function `_run_generate_us_tev_graphs_action(environment)` takes `environment` as a parameter, so the factory needs to call `get_or_create_utility_environment()` internally (like `_load_replace_images_runner` does), not receive it as an arg. The ticket should make this factory-wrapping explicit to avoid confusion.

**Severity**: Nit. An implementing agent reading the existing code will figure this out.

### N2. Ticket #004 blocked-by chain could be loosened

Ticket #004 (preview script refactor) is blocked by #003 (CLI wiring). But the script refactor only depends on the discovery engine from ticket #001 — it doesn't need the CLI utility action to exist. Unblocking #004 from #003 and instead blocking it on #001 would allow #004 to run in parallel with #002/#003, shortening the critical path.

**Severity**: Minor scheduling optimization. The linear chain works fine if parallelism isn't a priority.

### N3. `SubstationIsolatedBatchResiliencePolicy` is already a CONTEXT.md concept

The existing [CONTEXT.md](file:///C:/Users/ADAM/Desktop/pahang-cli/CONTEXT.md) already defines `SubstationIsolatedBatchResiliencePolicy` (for post-processing). Ticket #005 plans to add it as a new concept. The implementation should reference the existing policy rather than creating a duplicate entry — just note that this utility also follows the same policy.

**Severity**: Nit. Documentation hygiene.

### N4. ADR numbering assumption

Ticket #005 assumes the next ADR is `0006`. If another ADR has been merged before this feature lands, the number will collide. The implementing agent should check `docs/adr/` and pick the next available number.

**Severity**: Trivial.

### N5. GitHub Issues still [Local Draft]

Carried from v1. Per the repo's ticket lifecycle rules, issues should be opened via `gh issue create` before work begins on ticket #001.

**Severity**: Minor process step.

---

## Summary

| Category | Count | Detail |
|----------|-------|--------|
| Critical gaps | **0** | All 4 resolved |
| Medium gaps | **0** | All 5 resolved |
| Minor nits remaining | **5** | N1–N5 above |

**Recommendation**: Ship it. Create the GitHub issues, create the feature branch, and start ticket #001.
