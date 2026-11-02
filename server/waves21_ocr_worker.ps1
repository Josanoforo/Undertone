$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    [void][Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
    [void][Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]
    [void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
    [void][Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
    [void][Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
    [void][Windows.Storage.Streams.DataWriter, Windows.Storage.Streams, ContentType=WindowsRuntime]
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $languages = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag })
    if ($request.operation -eq 'capabilities') {
        [Console]::Out.Write((@{status='ok';languages=$languages;maxImageDimension=[Windows.Media.Ocr.OcrEngine]::MaxImageDimension} | ConvertTo-Json -Compress))
        exit 0
    }
    if ($request.operation -ne 'recognize' -or $request.language -notin $languages) { throw 'Unavailable operation' }
    function Await($operation, $resultType) {
        $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
            $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
        } | Select-Object -First 1
        $task = $method.MakeGenericMethod($resultType).Invoke($null, @($operation))
        return $task.GetAwaiter().GetResult()
    }
    Add-Type -AssemblyName System.Drawing
    $raw = [Convert]::FromBase64String($request.image)
    if ($raw.Length -gt 4194304) { throw 'Image bound' }
    $inputStream = [IO.MemoryStream]::new($raw, $false)
    $bitmap = [Drawing.Bitmap]::new($inputStream)
    $c = $request.crop
    if ($c.x -lt 0 -or $c.y -lt 0 -or $c.width -lt 1 -or $c.height -lt 1 -or
        $c.x+$c.width -gt $bitmap.Width -or $c.y+$c.height -gt $bitmap.Height -or
        $c.width -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension -or
        $c.height -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension) { throw 'Crop bound' }
    $rectangle = [Drawing.Rectangle]::new($c.x, $c.y, $c.width, $c.height)
    $cropped = $bitmap.Clone($rectangle, [Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $scale = [Math]::Min(3, [Math]::Floor([Windows.Media.Ocr.OcrEngine]::MaxImageDimension / [Math]::Max($c.width, $c.height)))
    $enlarged = [Drawing.Bitmap]::new($cropped, [int]($c.width*$scale), [int]($c.height*$scale))
    $png = [IO.MemoryStream]::new()
    $enlarged.Save($png, [Drawing.Imaging.ImageFormat]::Png)
    $stream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
    $writer = [Windows.Storage.Streams.DataWriter]::new($stream.GetOutputStreamAt(0))
    $writer.WriteBytes($png.ToArray())
    [void](Await ($writer.StoreAsync()) ([UInt32]))
    [void]$writer.DetachStream(); $writer.Dispose()
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $software = Await ($decoder.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8, [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied)) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $language = [Windows.Globalization.Language]::new($request.language)
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
    if ($null -eq $engine) { throw 'Recognizer unavailable' }
    $recognized = Await ($engine.RecognizeAsync($software)) ([Windows.Media.Ocr.OcrResult])
    $angle = $recognized.TextAngle
    if ($null -ne $angle -and [Math]::Abs([double]$angle) -gt 0.01) { throw 'Rotated text boxes unsupported' }
    $words = @()
    foreach ($line in $recognized.Lines) {
        foreach ($word in $line.Words) {
            if ($words.Count -ge 100) { throw 'Word bound' }
            $b = $word.BoundingRect
            $words += @{text=$word.Text;x=$b.X/$scale;y=$b.Y/$scale;width=$b.Width/$scale;height=$b.Height/$scale}
        }
    }
    [Console]::Out.Write((@{status='ok';language=$request.language;words=$words;textAngle=$angle} | ConvertTo-Json -Compress -Depth 5))
} catch {
    [Console]::Out.Write('{"status":"unavailable"}')
    exit 1
} finally {
    foreach ($resource in @($software,$stream,$png,$enlarged,$cropped,$bitmap,$inputStream)) {
        if ($null -ne $resource) { $resource.Dispose() }
    }
}
