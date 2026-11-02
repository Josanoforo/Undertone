$ErrorActionPreference = 'Stop'
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$request.textUtf8Base64))
if (-not $text -or $text.Length -gt 600) { throw 'text_length_out_of_bounds' }
$voice = New-Object -ComObject SAPI.SpVoice
$lang = [string]$request.language
$wanted = if ($lang -eq 'en') { 'TTS_MS_EN-US_ZIRA_11.0' } elseif ($lang -eq 'es') { 'TTS_MS_ES-MX_SABINA_11.0' } else { throw 'unsupported_language' }
$token = @($voice.GetVoices() | Where-Object { $_.Id -like "*$wanted" }) | Select-Object -First 1
if (-not $token) { throw 'required_voice_unavailable' }
$voice.Voice = $token
$voice.Rate = 0
$voice.Volume = 100
$stream = New-Object -ComObject SAPI.SpFileStream
$format = New-Object -ComObject SAPI.SpAudioFormat
$format.Type = 18
$stream.Format = $format
$stream.Open([string]$request.output, 3, $false)
$voice.AudioOutputStream = $stream
[void]$voice.Speak($text, 16)
$stream.Close()
[Console]::Out.WriteLine((@{voiceId=$token.Id;voiceName=$token.GetDescription();language=$lang;format='PCM16_16000_mono'} | ConvertTo-Json -Compress))
