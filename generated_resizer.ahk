
#Requires AutoHotkey v2.0
#SingleInstance Force
#NoTrayIcon

WindowSettings := Map()


ExcludeTitles := []
ProcessedWindows := Map()

CheckAllWindows() {
    try {
        for hwnd in WinGetList() {
            try {
                if (ProcessedWindows.Has(hwnd) || !WinExist("ahk_id " . hwnd))
                    continue
                title := WinGetTitle("ahk_id " . hwnd)
                windowClass := WinGetClass("ahk_id " . hwnd)
                if (IsExcludedTitle(title))
                    continue
                for _, settings in WindowSettings {
                    if (windowClass = settings.class && IsTargetTitle(title, settings.titles)) {
                        ResizeWindow(hwnd, settings.width, settings.height, settings.position)
                        ProcessedWindows[hwnd] := A_TickCount
                        break
                    }
                }
            } catch {
                continue
            }
        }
        CleanupOldWindows()
    } catch {
        ; Этот пустой блок catch необходим для синтаксической корректности.
    }
}

IsTargetTitle(title, titlesList) {
    for _, targetTitle in titlesList
        if InStr(title, targetTitle)
            return true
    return false
}

IsExcludedTitle(title) {
    for _, excludeTitle in ExcludeTitles
        if InStr(title, excludeTitle) > 0
            return true
    return false
}

ResizeWindow(hwnd, targetWidth, targetHeight, position) {
    try {
        WinGetPos(&x, &y, &width, &height, "ahk_id " . hwnd)
        local newX, newY, topOffset := 40
        switch position {
            case "left": newX := 0, newY := (A_ScreenHeight - targetHeight) // 2
            case "center": newX := (A_ScreenWidth - targetWidth) // 2, newY := (A_ScreenHeight - targetHeight) // 2
            case "right": newX := A_ScreenWidth - targetWidth, newY := (A_ScreenHeight - targetHeight) // 2
            case "top-left": newX := 0, newY := topOffset
            case "top-center": newX := (A_ScreenWidth - targetWidth) // 2, newY := topOffset
            case "top-right": newX := A_ScreenWidth - targetWidth, newY := topOffset
            case "bottom-left": newX := 0, newY := A_ScreenHeight - targetHeight
            case "bottom-center": newX := (A_ScreenWidth - targetWidth) // 2, newY := A_ScreenHeight - targetHeight
            case "bottom-right": newX := A_ScreenWidth - targetWidth, newY := A_ScreenHeight - targetHeight
            default: newX := (A_ScreenWidth - targetWidth) // 2, newY := (A_ScreenHeight - targetHeight) // 2
        }
        if (width != targetWidth || height != targetHeight || x != newX || y != newY) {
            ; WinActivate("ahk_id " . hwnd)
            ; Sleep(50)
            WinMove(newX, newY, targetWidth, targetHeight, "ahk_id " . hwnd)
        }
    } catch {
    }
}

CleanupOldWindows() {
    toRemove := []
    for hwnd, timestamp in ProcessedWindows
        if (!WinExist("ahk_id " . hwnd) || (A_TickCount - timestamp > 30000))
            toRemove.Push(hwnd)
    for _, hwnd in toRemove
        ProcessedWindows.Delete(hwnd)
}

SetTimer(CheckAllWindows, 1000)
return
