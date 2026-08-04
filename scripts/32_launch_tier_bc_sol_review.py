from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "launch_tier_bc_sol_main",
            module_name="prta_cxr.tier_bc_sol_review",
        )
    )
