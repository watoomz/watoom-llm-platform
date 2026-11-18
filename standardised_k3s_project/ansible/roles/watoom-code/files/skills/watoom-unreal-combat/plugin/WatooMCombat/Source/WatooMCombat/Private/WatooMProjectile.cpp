#include "WatooMProjectile.h"
#include "WatooMAbilities.h"
#include "WatooMCombatData.h"
#include "WatooMCombatCharacter.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Character.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "Net/UnrealNetwork.h"
#include "NiagaraComponent.h"

AWatooMProjectile::AWatooMProjectile()
{
	bReplicates = true;
	SetReplicateMovement(true);
	Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
	Collision->InitSphereRadius(12.f);
	Collision->SetCollisionProfileName(TEXT("BlockAllDynamic"));   // stops on the world (OnHit) ...
	Collision->SetCollisionResponseToChannel(ECC_Pawn, ECR_Overlap); // ... and passes into characters (OnOverlap)
	Collision->SetGenerateOverlapEvents(true);
	RootComponent = Collision;
	Movement = CreateDefaultSubobject<UProjectileMovementComponent>(TEXT("Movement"));
	Movement->InitialSpeed = 2500.f;
	Movement->MaxSpeed = 2500.f;
	Movement->ProjectileGravityScale = 0.f;
	Movement->bRotationFollowsVelocity = true;
	Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
	Body->SetupAttachment(Collision);
	Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Trail = CreateDefaultSubobject<UNiagaraComponent>(TEXT("Trail"));
	Trail->SetupAttachment(Collision);
	Trail->bAutoActivate = false;
	InitialLifeSpan = 5.f;
}

void AWatooMProjectile::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AWatooMProjectile, Spell);
	DOREPLIFETIME(AWatooMProjectile, Weapon);
}

void AWatooMProjectile::InitFromSpell(UWatooMSpellData* InSpell, UWatooMGA_Spell* InAbility)
{
	Spell = InSpell;
	Ability = InAbility;
	if (Spell)
	{
		Movement->InitialSpeed = Movement->MaxSpeed = FMath::Max(Spell->ProjectileSpeed, 1.f);
		Movement->Velocity = GetActorForwardVector() * Movement->InitialSpeed;
		SetLifeSpan(FMath::Clamp(Spell->Range / Movement->InitialSpeed, 0.2f, 10.f));
	}
	if (GetInstigator()) { Collision->IgnoreActorWhenMoving(GetInstigator(), true); }
	Collision->OnComponentHit.AddDynamic(this, &AWatooMProjectile::OnHit);
	Collision->OnComponentBeginOverlap.AddDynamic(this, &AWatooMProjectile::OnOverlap);
	OnRep_Spell();
}

void AWatooMProjectile::InitFromWeapon(UWatooMWeaponData* InWeapon, UWatooMGameplayAbility* InAbility)
{
	Weapon = InWeapon;
	WeaponAbility = InAbility;
	if (Weapon)
	{
		Movement->InitialSpeed = Movement->MaxSpeed = FMath::Max(Weapon->ProjectileSpeed, 1.f);
		Movement->ProjectileGravityScale = Weapon->ProjectileGravityScale;
		Movement->Velocity = GetActorForwardVector() * Movement->InitialSpeed;
		SetLifeSpan(FMath::Clamp(Weapon->Range / Movement->InitialSpeed, 0.2f, 10.f));
		Collision->SetSphereRadius(6.f);
	}
	if (GetInstigator()) { Collision->IgnoreActorWhenMoving(GetInstigator(), true); }
	Collision->OnComponentHit.AddDynamic(this, &AWatooMProjectile::OnHit);
	Collision->OnComponentBeginOverlap.AddDynamic(this, &AWatooMProjectile::OnOverlap);
	OnRep_Weapon();
}

void AWatooMProjectile::OnRep_Weapon()
{
	if (!Weapon) { return; }
	if (Weapon->ProjectileMesh) { Body->SetStaticMesh(Weapon->ProjectileMesh); }
	if (Weapon->TracerFx)
	{
		Trail->SetAsset(Weapon->TracerFx);
		Trail->Activate(true);
	}
}

void AWatooMProjectile::OnRep_Spell()
{
	if (Spell && Spell->ProjectileFx)
	{
		Trail->SetAsset(Spell->ProjectileFx);
		Trail->Activate(true);
	}
}

void AWatooMProjectile::OnHit(UPrimitiveComponent* HitComp, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit)
{
	Impact(Hit.ImpactPoint, OtherActor);
}

void AWatooMProjectile::OnOverlap(UPrimitiveComponent* OverlappedComp, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	if (OtherActor && OtherActor != GetInstigator() && OtherActor != this) { Impact(GetActorLocation(), OtherActor); }
}

void AWatooMProjectile::Impact(const FVector& Point, AActor* Direct)
{
	if (!HasAuthority() || bDone) { return; }
	bDone = true;
	if (UWatooMGA_Spell* A = Ability.Get()) { A->HitTargetsAt(Point, Direct == GetInstigator() ? nullptr : Direct, Spell.Get()); }
	if (UWatooMGameplayAbility* A = WeaponAbility.Get(); A && Weapon)
	{
		AActor* Target = Direct == GetInstigator() ? nullptr : Direct;
		float Mult = 1.f;
		if (const ACharacter* HitChar = Cast<ACharacter>(Target))
		{
			const USkeletalMeshComponent* M = HitChar->GetMesh();
			if (M && M->DoesSocketExist(Weapon->HeadBone) && FVector::Dist(M->GetSocketLocation(Weapon->HeadBone), Point) < 25.f)
			{
				Mult = Weapon->HeadshotMultiplier;
			}
		}
		if (Target) { A->ApplyDamage(Target, Weapon->Damage, Mult, Weapon->DamageType); }
		if (AWatooMCombatCharacter* C = Cast<AWatooMCombatCharacter>(GetInstigator()))
		{
			C->MulticastPlayFx(Weapon->ImpactFx.Niagara, Weapon->ImpactFx.Sound, Point, GetActorRotation(), Weapon->ImpactFx.Scale);
		}
	}
	Destroy();
}
