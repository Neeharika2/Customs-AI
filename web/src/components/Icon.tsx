import type { SVGProps } from "react";

type IconName =
  | "box"
  | "file"
  | "check"
  | "alert"
  | "block"
  | "chevron-down"
  | "chevron-right"
  | "search"
  | "plus"
  | "arrow-left"
  | "arrow-right"
  | "user"
  | "settings"
  | "chart"
  | "logout"
  | "clock"
  | "eye"
  | "x"
  | "spark"
  | "download"
  | "upload"
  | "refresh";

const paths: Record<IconName, string> = {
  box: "M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5v-9Z M3.5 7.5 12 12l8.5-4.5 M12 12v9",
  file: "M6 3h8l4 4v14H6V3Z M14 3v5h5",
  check: "m5 12.5 4.5 4.5L19 7",
  alert: "M12 4 2.8 20h18.4L12 4Z M12 9.5v4.5 M12 17.2v.2",
  block: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z M6 6l12 12",
  "chevron-down": "m6 9 6 6 6-6",
  "chevron-right": "m9 6 6 6-6 6",
  search: "M10.8 18.2a7.4 7.4 0 1 0 0-14.8 7.4 7.4 0 0 0 0 14.8Z M16.2 16.2 21 21",
  plus: "M12 5v14 M5 12h14",
  "arrow-left": "M19 12H5 M11 6l-6 6 6 6",
  "arrow-right": "M5 12h14 M13 6l6 6-6 6",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z M4.5 21a7.5 7.5 0 0 1 15 0",
  settings:
    "M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1 1.56V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.9 19.3a1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.7 8.9a1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.56V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9v.09a1.7 1.7 0 0 0 1.56 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1Z",
  chart: "M4 20V10 M10 20V4 M16 20v-7 M22 20H2",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4 M16 17l5-5-5-5 M21 12H9",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z M12 7v5l3 2",
  eye: "M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  x: "M18 6 6 18 M6 6l12 12",
  spark: "M12 3v4 M12 17v4 M3 12h4 M17 12h4 M6 6l2.5 2.5 M15.5 15.5 18 18 M18 6l-2.5 2.5 M8.5 15.5 6 18",
  download: "M12 3v12 M7 10l5 5 5-5 M4 21h16",
  upload: "M12 21V9 M7 14l5-5 5 5 M4 3h16",
  refresh: "M20 11a8 8 0 1 0-2.3 6.3 M20 4v7h-7",
};

export function Icon({
  name,
  size = 18,
  ...props
}: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d={paths[name]} />
    </svg>
  );
}
