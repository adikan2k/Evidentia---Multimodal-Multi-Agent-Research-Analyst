import { redirect } from "next/navigation";

// The auditor used to live here. It is the home page now; old links still arrive.
export default function Page() {
  redirect("/");
}
