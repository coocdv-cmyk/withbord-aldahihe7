$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
Add-Type -ReferencedAssemblies System.Speech -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Speech.Synthesis;
public class DemoSpeech {
 public static List<string> Events = new List<string>();
 public static void Run(string file) {
  using(var s=new SpeechSynthesizer()) {
   s.SelectVoice("Microsoft Zira Desktop"); s.Rate=-1;
   s.VisemeReached += (o,e) => Events.Add("{\"t\":"+e.AudioPosition.TotalSeconds.ToString(System.Globalization.CultureInfo.InvariantCulture)+",\"id\":"+e.Viseme+",\"duration\":"+e.Duration.TotalSeconds.ToString(System.Globalization.CultureInfo.InvariantCulture)+"}");
   s.SetOutputToWaveFile(file);
   s.Speak("A convincing story can feel like proof. But confidence and evidence are different things. Imagine two explanations. One sounds impressive. The other can be checked. Before we accept a claim, we should ask what would prove it wrong. That is how a good question becomes a better explanation.");
  }
 }
}
'@
$taskOutput = Split-Path $PSScriptRoot -Parent
try { [DemoSpeech]::Run((Join-Path $taskOutput 'audio/narration.wav')) }
catch { Write-Output $_.Exception.InnerException.ToString(); throw }
('[' + ([DemoSpeech]::Events -join ',') + ']') | Set-Content -LiteralPath (Join-Path $taskOutput 'audio/visemes.json') -Encoding UTF8
