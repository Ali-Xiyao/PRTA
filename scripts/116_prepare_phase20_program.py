from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_phase20_program_main",
            module_name="prta_cxr.phase20_program",
        )
    )
