param(
    [string]$SourcePath = "kaggle/illustrious_xl_style_lora.py",
    [string]$NotebookPath = "kaggle/illustrious_xl_style_lora.ipynb"
)

$ErrorActionPreference = "Stop"
python tools/sync_kaggle_notebook.py --source $SourcePath --notebook $NotebookPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
