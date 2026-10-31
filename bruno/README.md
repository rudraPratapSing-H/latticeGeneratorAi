# Bruno collection

1. Start the server: `.\scripts\dev.ps1` (real models, GPU laptop) or `.\scripts\dev.ps1 -Mock` (canned results and the stored demo targets, no GPU).
2. In Bruno: Open Collection -> choose this `bruno` folder, pick the `local` environment.
3. Run 1 Health, 2 Materials, 9 Limits, 10 Reach, 3 Create design, 4 Get job (repeat until done), 6 Get design. 5 streams progress; 11 cancels a job.
4. 8 and 12 show the infeasible-target rule (422 without `force`, 202 with it). Sending request 3 twice returns the same job (cache).
5. `errors/` holds requests that must return 404 or 422 with `{"error": {"code", "message"}}`. `dataset/` holds targets taken from stored lattices (D1-D8, X1-X2).
