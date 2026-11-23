# Third-party notices

## AnimeStudio format adapter

`scripts/sprite_bundle.py` adapts ENCR/mr0k format and decoding logic from
[Escartem/AnimeStudio](https://github.com/Escartem/AnimeStudio), pinned at
`76234e9f6f5a839504f41f9612719529fe2309a5` (`BundleFile.cs`, `Mr0kUtils.cs`,
`Crypto/AES.cs`, `Crypto/CryptoHelper.cs`). The two upstream table files are
fetched only by the explicit `prepare-codec` command and SHA-256 verified;
they are not redistributed here.

MIT License

Copyright (c) 2016 Radu
Copyright (c) 2016-2020 Perfare
Copyright (c) 2022-2024 Razmoth
Copyright (c) 2024-2026 Escartem

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Other dependencies and format references

- UnityPy parses Unity serialized objects and reconstructs Sprites, including
  atlas, trim and packing metadata; its dependency licenses remain applicable.
- pyooz/ooz handles Oodle-family decompression; lz4 handles LZ4;
  texture2ddecoder handles encoded textures. See their distributions for licenses.
- SRAM table layout was cross-checked against the maintained
  [CollapseLauncher StarRailAssetBundleMetadata](https://github.com/CollapseLauncher/Collapse/blob/b4a3805a4af0a9f382f907fb518a5ecb11c13f30/CollapseLauncher/Classes/RepairManagement/StarRailV2/Struct/Assets/StarRailAssetBundleMetadata.cs)
  and StarRailAssetBlockMetadata at the same revision. No launcher code is copied.
  Offset/length/dependency fields are additionally checked against decoded bundles.

Game assets are not distributed and are not covered by these code licenses.
