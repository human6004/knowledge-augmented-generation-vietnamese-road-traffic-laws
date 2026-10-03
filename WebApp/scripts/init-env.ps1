param([switch]$Kag, [switch]$Update)
# Keep existing WebApp commands working; the shared initializer lives at root/docker.
& "$PSScriptRoot/../../docker/init-env.ps1" @PSBoundParameters
