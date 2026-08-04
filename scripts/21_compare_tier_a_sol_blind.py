from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "compare_tier_a_sol_main",
            module_name="prta_cxr.tier_a_sol_review",
        )
    )
