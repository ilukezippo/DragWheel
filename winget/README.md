# winget listing

These are the three files Microsoft's Windows Package Manager needs to list DragWheel, so anyone can install it with:

```
winget install DragWheel
```

## Submitting (once per release)

1. Fork https://github.com/microsoft/winget-pkgs on GitHub.
2. In your fork, add the folder `manifests/i/ilukezippo/DragWheel/1.2.0/` with the three `.yaml` files from here
   (GitHub's **Add file → Upload files** works; type the folder path in the file name box).
3. Open a pull request to microsoft/winget-pkgs titled `New package: ilukezippo.DragWheel version 1.2.0`.
4. Microsoft's bots install and scan the package automatically. A reviewer merges it, usually within a few days.

For later versions, copy the folder to the new version number and change `PackageVersion`, `DisplayVersion`,
`InstallerUrl`, `InstallerSha256` and `ReleaseDate`. The SHA-256 is shown next to the installer on the GitHub release page.

Shortcut: the `wingetcreate` tool does all of this from one command:
`wingetcreate update ilukezippo.DragWheel --version 1.2.0 --urls <installer url> --submit`
