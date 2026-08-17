from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("prepare_phase16_program_main", module_name="prta_cxr.phase16_program")
    )
