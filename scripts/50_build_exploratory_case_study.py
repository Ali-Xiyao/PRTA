from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "case_study_main",
            module_name="prta_cxr.case_study",
        )
    )
