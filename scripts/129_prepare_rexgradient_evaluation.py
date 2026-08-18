from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_external_program_main",
            module_name="prta_cxr.rexgradient_evaluation",
        )
    )
