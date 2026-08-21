from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "phase20_evidence_finalize_main",
            module_name="prta_cxr.phase20_evidence_finalize",
        )
    )
