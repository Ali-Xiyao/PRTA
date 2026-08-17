from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("finalize_phase16_main", module_name="prta_cxr.phase16_finalize")
    )
