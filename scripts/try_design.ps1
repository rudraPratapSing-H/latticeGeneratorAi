# Send one design request, wait for it, print the designs.
#   .\scripts\try_design.ps1 -Index 2            # request D2 from bruno\dataset_requests.json (1..8)
#   .\scripts\try_design.ps1 -File mybody.json   # your own JSON body
param(
  [int]$Index = 2,
  [string]$File = "",
  [string]$Base = "http://localhost:8000"
)
$root = Split-Path -Parent $PSScriptRoot
if ($File -ne "") {
  $body = Get-Content -Raw -Path $File
} else {
  $all = Get-Content -Raw -Path (Join-Path $root "bruno\dataset_requests.json") | ConvertFrom-Json
  $body = $all[$Index - 1].body | ConvertTo-Json -Depth 10
  Write-Host ("request D{0}: {1}" -f $Index, $all[$Index - 1].label)
}
$t0 = Get-Date
$job = Invoke-RestMethod -Method Post -Uri "$Base/api/designs" -ContentType "application/json" -Body $body
Write-Host ("job: " + $job.job_id)
do {
  Start-Sleep -Milliseconds 1000
  $j = Invoke-RestMethod -Uri ("$Base/api/jobs/" + $job.job_id)
  $sec = [math]::Round(((Get-Date) - $t0).TotalSeconds)
  Write-Host ("{0,4}s  {1,-8} {2,-7} {3,4:P0}  {4}" -f $sec, $j.status, $j.stage, $j.progress, $j.message)
} while ($j.status -ne "done" -and $j.status -ne "failed")
foreach ($c in $j.candidates) {
  $e = $c.verified.stiffness_gpa; $s = $c.verified.strength_mpa
  Write-Host ("rank {0} match={1,-5} err={2,6}%  rho={3}  mass={4}g  E=({5:N2},{6:N2},{7:N2}) GPa  S=({8:N1},{9:N1},{10:N1}) MPa  [{11}]" -f `
    $c.rank, $c.matches_targets, $c.match_error_pct, $c.rel_density, $c.mass_g, $e.x, $e.y, $e.z, $s.x, $s.y, $s.z, $c.origin)
}
