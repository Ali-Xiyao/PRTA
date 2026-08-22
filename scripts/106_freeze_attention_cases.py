from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "attention_preselection_main",
            module_name="prta_cxr.attention_flow",
        )
    )
