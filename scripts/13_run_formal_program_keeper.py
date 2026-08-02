from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("program_keeper_main", module_name="prta_cxr.cli_program_keeper")
    )
