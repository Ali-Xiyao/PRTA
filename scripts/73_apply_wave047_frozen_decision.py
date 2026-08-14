from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "apply_wave047_frozen_decision_main",
            module_name="prta_cxr.wave047_frozen_decision",
        )
    )
