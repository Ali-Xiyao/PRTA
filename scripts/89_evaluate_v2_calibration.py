from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "calibration_evidence_main",
            module_name="prta_cxr.v2_calibration_evidence",
        )
    )
