from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "apply_tier_a_sol_labels_main",
            module_name="prta_cxr.tier_a_sol_review",
        )
    )
