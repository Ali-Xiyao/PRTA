from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "compare_sol_review_main",
            module_name="prta_cxr.cli_sol_review",
        )
    )
