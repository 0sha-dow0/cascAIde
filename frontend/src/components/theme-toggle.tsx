import { Button } from "@/components/ui/button";
import { Moon, Sun } from "@/components/icons";
import { useTheme } from "@/components/theme-provider";

export function ThemeToggle() {
  const { isDark, setTheme } = useTheme();
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Toggle theme"
      title="Toggle theme"
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {isDark ? <Sun /> : <Moon />}
    </Button>
  );
}
