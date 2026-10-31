# Bruno collection

1. Start the server: `uvicorn server.app:app --port 8000` (add `MOCK=1` for canned results with no GPU).
2. In Bruno: Open Collection -> choose this `bruno` folder, pick the `local` environment.
3. Run 1 -> 2 -> 3 -> 4 (repeat 4 until done) -> 6. The `errors` folder holds requests that must return 404 or 422.
