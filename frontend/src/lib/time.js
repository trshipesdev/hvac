import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";

dayjs.extend(utc);
dayjs.extend(timezone);

const DEFAULT_TZ = "UTC";

function tzOf(property) {
  return property?.timezone || DEFAULT_TZ;
}

function timeFmt(property) {
  return property?.use_24h_time ? "HH:mm" : "h:mm A";
}

// Real UTC ISO timestamp -> local date + time, e.g. "Jul 5, 2026, 8:00 PM"
export function fmtDateTime(isoUtc, property) {
  if (!isoUtc) return "—";
  return dayjs.utc(isoUtc).tz(tzOf(property)).format(`MMM D, YYYY, ${timeFmt(property)}`);
}

// Real UTC ISO timestamp -> local time only, e.g. "8:00 PM"
export function fmtTimeOnly(isoUtc, property) {
  if (!isoUtc) return "—";
  return dayjs.utc(isoUtc).tz(tzOf(property)).format(timeFmt(property));
}

// Real UTC ISO timestamp -> local date only, e.g. "2026-07-05"
export function fmtDateOnly(isoUtc, property) {
  if (!isoUtc) return "—";
  return dayjs.utc(isoUtc).tz(tzOf(property)).format("YYYY-MM-DD");
}

// A bucket key from /dashboard/timeline ("YYYY-MM-DD HH:00" or "YYYY-MM-DD")
// is ALREADY in the property's local time (the backend localizes it) — do
// NOT run it through .tz() again here, just reformat for 12h/24h display.
export function fmtBucketLabel(bucketKey, bucketKind, property) {
  if (!bucketKey) return "";
  if (bucketKind === "day") {
    return dayjs(bucketKey).format("MMM D");
  }
  const naive = dayjs(bucketKey.replace(" ", "T"));
  return naive.format(timeFmt(property));
}
