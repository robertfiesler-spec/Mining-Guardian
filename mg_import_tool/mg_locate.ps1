# Locate the exact line numbers of the Layer 2 call site and the streaming
# endpoint in the PC's patched mg_import.py, so the patch targets real lines.

$File = 'C:\Users\User\Mining-Guardian\mg_import_tool\mg_import.py'

Write-Host ''
Write-Host '================================================================'
Write-Host '  File info'
Write-Host '================================================================'
Get-Item $File | Select-Object FullName, Length, LastWriteTime | Format-List

Write-Host ''
Write-Host '================================================================'
Write-Host '  Layer 2 / process_archive / streaming endpoint line numbers'
Write-Host '================================================================'
Select-String -Path $File -Pattern 'def process_archive|def import_files_stream|def import_files\b|def _do_layer2_postprocessing|_do_layer2_postprocessing\(|sql_blocks\.append\(.BEGIN|if conn_params:|process_archive\(data, filename|execute_sql_block\(conn_params,' |
  Select-Object LineNumber, Line | Format-Table -AutoSize -Wrap

Write-Host ''
Write-Host '================================================================'
Write-Host '  Context around the Layer 2 call site in process_archive'
Write-Host '================================================================'
Select-String -Path $File -Pattern 'if conn_params:\s*$' -Context 3,8 |
  ForEach-Object { $_.Context.PreContext; "  >>> $($_.LineNumber): $($_.Line)"; $_.Context.PostContext; "---" }

Write-Host ''
Write-Host '================================================================'
Write-Host '  Context around process_archive() call in import_files_stream'
Write-Host '================================================================'
Select-String -Path $File -Pattern 'process_archive\(data, filename' -Context 2,8 |
  ForEach-Object { $_.Context.PreContext; "  >>> $($_.LineNumber): $($_.Line)"; $_.Context.PostContext; "---" }
